from __future__ import annotations

from abc import ABC, abstractmethod

from signal2noise.entities import Mode, ProjectState


class BasePolicy(ABC):
    @abstractmethod
    def initial_mode(self) -> Mode:
        raise NotImplementedError

    @abstractmethod
    def step(self, project: ProjectState, t: int) -> Mode | None:
        raise NotImplementedError


class AsyncOnlyPolicy(BasePolicy):
    def initial_mode(self) -> Mode:
        return Mode.ASYNC

    def step(self, project: ProjectState, t: int) -> Mode | None:
        return None


class AlwaysSyncPolicy(BasePolicy):
    def initial_mode(self) -> Mode:
        return Mode.SYNC

    def step(self, project: ProjectState, t: int) -> Mode | None:
        return None


class PeriodicSyncPolicy(BasePolicy):
    def __init__(
        self,
        period: int,
        sync_ticks: int,
        stress_level: float = 1.0,
        period_by_stress: dict[float, int] | None = None,
        sync_ticks_by_stress: dict[float, int] | None = None,
    ):
        self.stress_level = stress_level
        self.period_by_stress = period_by_stress or {}
        self.sync_ticks_by_stress = sync_ticks_by_stress or {}
        self.period = max(1, int(period))
        self.sync_ticks = max(0, int(sync_ticks))
        self._resolve_schedule()

    def _closest_key(self, mapping: dict[float, int], target: float) -> float | None:
        if not mapping:
            return None
        return min(mapping.keys(), key=lambda k: abs(k - target))

    def _resolve_schedule(self) -> None:
        p_key = self._closest_key(self.period_by_stress, self.stress_level)
        if p_key is not None:
            self.period = max(1, int(self.period_by_stress[p_key]))

        s_key = self._closest_key(self.sync_ticks_by_stress, self.stress_level)
        if s_key is not None:
            self.sync_ticks = max(0, int(self.sync_ticks_by_stress[s_key]))

        self.sync_ticks = min(self.sync_ticks, self.period)

    def _desired_mode(self, t: int) -> Mode:
        return Mode.SYNC if (t % self.period) < self.sync_ticks else Mode.ASYNC

    def initial_mode(self) -> Mode:
        return self._desired_mode(0)

    def step(self, project: ProjectState, t: int) -> Mode | None:
        desired = self._desired_mode(t)
        if desired != project.mode:
            return desired
        return None


class SwarmPolicy(BasePolicy):
    def __init__(
        self,
        W: int,
        T_enter: float,
        T_exit: float,
        K: int,
        trigger_metric: str = "rework_rate",
        snr_epsilon: float = 1e-6,
        use_gap_gate: bool = False,
        gap_gate_mode: str = "and",
        gap_enter_threshold: float = 0.0,
        gap_window: int = 1,
        cooldown_ticks: int = 0,
    ):
        self.W = W
        self.T_enter = T_enter
        self.T_exit = T_exit
        self.K = K
        self.trigger_metric = trigger_metric
        self.snr_epsilon = max(1e-12, snr_epsilon)
        self.use_gap_gate = bool(use_gap_gate)
        self.gap_gate_mode = str(gap_gate_mode).lower().strip()
        if self.gap_gate_mode not in {"and", "or"}:
            self.gap_gate_mode = "and"
        self.gap_enter_threshold = float(gap_enter_threshold)
        self.gap_window = max(1, int(gap_window))
        self.cooldown_ticks = max(0, int(cooldown_ticks))
        self._below_exit_streak = 0
        self._cooldown_until_t = -1

    def initial_mode(self) -> Mode:
        return Mode.ASYNC

    def _rework_rate(self, project: ProjectState) -> float:
        if self.W <= 0:
            return 0.0
        series = project.rework_events_per_tick
        if not series:
            return 0.0
        window = series[-self.W :]
        return sum(window) / float(self.W)

    def _signal_noise_ratio(self, project: ProjectState) -> float:
        if self.W <= 0:
            return 0.0
        signal = project.signal_events_per_tick
        noise = project.noise_events_per_tick
        if not signal:
            return 0.0
        s_window = signal[-self.W :]
        n_window = noise[-self.W :] if noise else []
        s_sum = float(sum(s_window))
        n_sum = float(sum(n_window))
        return s_sum / (n_sum + self.snr_epsilon)

    def _trigger_value(self, project: ProjectState) -> float:
        if self.trigger_metric == "snr":
            return self._signal_noise_ratio(project)
        return self._rework_rate(project)

    def _gap_level(self, project: ProjectState) -> float:
        if not project.gap_per_tick:
            return 0.0
        window = project.gap_per_tick[-self.gap_window :]
        return sum(window) / float(len(window))

    def _enter_condition(self, signal: float, gap: float) -> bool:
        signal_ok = signal >= self.T_enter
        if not self.use_gap_gate:
            return signal_ok
        gap_ok = gap >= self.gap_enter_threshold
        if self.gap_gate_mode == "or":
            return signal_ok or gap_ok
        return signal_ok and gap_ok

    def step(self, project: ProjectState, t: int) -> Mode | None:
        if t <= self._cooldown_until_t:
            return None

        signal = self._trigger_value(project)
        gap = self._gap_level(project)
        if project.mode == Mode.ASYNC and self._enter_condition(signal, gap):
            self._below_exit_streak = 0
            self._cooldown_until_t = t + self.cooldown_ticks
            return Mode.SYNC
        if project.mode == Mode.SYNC:
            if signal <= self.T_exit:
                self._below_exit_streak += 1
                if self._below_exit_streak >= self.K:
                    self._below_exit_streak = 0
                    self._cooldown_until_t = t + self.cooldown_ticks
                    return Mode.ASYNC
            else:
                self._below_exit_streak = 0
        return None


class NaiveTriggerPolicy(BasePolicy):
    def __init__(self, W: int = 5, K: int = 2):
        self.W = max(1, int(W))
        self.K = max(1, int(K))
        self._zero_streak = 0

    def initial_mode(self) -> Mode:
        return Mode.ASYNC

    def _recent_rework(self, project: ProjectState) -> int:
        series = project.rework_events_per_tick
        if not series:
            return 0
        return int(sum(series[-self.W :]))

    def step(self, project: ProjectState, t: int) -> Mode | None:
        if project.mode == Mode.ASYNC:
            if self._recent_rework(project) > 0:
                self._zero_streak = 0
                return Mode.SYNC
            return None

        # In SYNC: leave only after sustained zero-rework window.
        if self._recent_rework(project) == 0:
            self._zero_streak += 1
            if self._zero_streak >= self.K:
                self._zero_streak = 0
                return Mode.ASYNC
        else:
            self._zero_streak = 0
        return None


def build_policy(policy_cfg: dict) -> BasePolicy:
    ptype = str(policy_cfg.get("type", "async_only"))
    if ptype == "async_only":
        return AsyncOnlyPolicy()
    if ptype == "always_sync":
        return AlwaysSyncPolicy()
    if ptype == "swarm":
        return SwarmPolicy(
            W=int(policy_cfg.get("W", 30)),
            T_enter=float(policy_cfg.get("T_enter", 0.15)),
            T_exit=float(policy_cfg.get("T_exit", 0.05)),
            K=int(policy_cfg.get("K", 10)),
            trigger_metric=str(policy_cfg.get("trigger_metric", "rework_rate")),
            snr_epsilon=float(policy_cfg.get("snr_epsilon", 1e-6)),
            use_gap_gate=bool(policy_cfg.get("use_gap_gate", False)),
            gap_gate_mode=str(policy_cfg.get("gap_gate_mode", "and")),
            gap_enter_threshold=float(policy_cfg.get("gap_enter_threshold", 0.0)),
            gap_window=int(policy_cfg.get("gap_window", 1)),
            cooldown_ticks=int(policy_cfg.get("cooldown_ticks", 0)),
        )
    if ptype == "naive_trigger":
        return NaiveTriggerPolicy(
            W=int(policy_cfg.get("W", 5)),
            K=int(policy_cfg.get("K", 2)),
        )
    if ptype == "periodic_sync":
        def _parse_float_keyed_int_map(obj: object) -> dict[float, int]:
            if not isinstance(obj, dict):
                return {}
            out: dict[float, int] = {}
            for k, v in obj.items():
                ks = str(k).strip()
                if (ks.startswith('"') and ks.endswith('"')) or (ks.startswith("'") and ks.endswith("'")):
                    ks = ks[1:-1]
                out[float(ks)] = int(v)
            return out

        return PeriodicSyncPolicy(
            period=int(policy_cfg.get("period", 20)),
            sync_ticks=int(policy_cfg.get("sync_ticks", 1)),
            stress_level=float(policy_cfg.get("stress_level", 1.0)),
            period_by_stress=_parse_float_keyed_int_map(policy_cfg.get("period_by_stress")),
            sync_ticks_by_stress=_parse_float_keyed_int_map(policy_cfg.get("sync_ticks_by_stress")),
        )
    raise ValueError(f"Unsupported policy type: {ptype}")
