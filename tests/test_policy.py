from __future__ import annotations

from signal2noise.entities import Mode, ProjectState
from signal2noise.policies import NaiveTriggerPolicy, PeriodicSyncPolicy, SwarmPolicy, build_policy


def make_project(mode: Mode, series: list[int]) -> ProjectState:
    p = ProjectState(run_id=0, mode=mode, agents={}, tasks={})
    p.rework_events_per_tick = list(series)
    p.signal_events_per_tick = []
    p.noise_events_per_tick = []
    p.gap_per_tick = []
    return p


def test_swarm_hysteresis_enter_exit():
    policy = SwarmPolicy(W=3, T_enter=0.5, T_exit=0.05, K=3)

    p = make_project(Mode.ASYNC, [0, 2, 2])
    assert policy.step(p, t=10) == Mode.SYNC

    p.mode = Mode.SYNC
    p.rework_events_per_tick.extend([0, 0, 0])
    assert policy.step(p, t=11) is None
    assert policy.step(p, t=12) is None
    assert policy.step(p, t=13) == Mode.ASYNC


def test_swarm_snr_trigger_enter_and_exit():
    policy = SwarmPolicy(W=3, T_enter=2.0, T_exit=0.5, K=2, trigger_metric="snr", snr_epsilon=1e-6)
    p = make_project(Mode.ASYNC, [0, 0, 0])
    p.signal_events_per_tick = [2, 2, 1]
    p.noise_events_per_tick = [0, 1, 0]
    assert policy.step(p, t=10) == Mode.SYNC

    p.mode = Mode.SYNC
    p.signal_events_per_tick.extend([0, 0])
    p.noise_events_per_tick.extend([2, 2])
    assert policy.step(p, t=11) is None
    assert policy.step(p, t=12) == Mode.ASYNC


def test_naive_trigger_switches_on_any_recent_rework():
    policy = NaiveTriggerPolicy(W=2, K=2)
    p = make_project(Mode.ASYNC, [0, 1])
    assert policy.step(p, t=4) == Mode.SYNC

    p.mode = Mode.SYNC
    p.rework_events_per_tick.extend([0, 0])
    assert policy.step(p, t=5) is None
    assert policy.step(p, t=6) == Mode.ASYNC


def test_swarm_gap_gate_blocks_enter_until_gap_is_high():
    policy = SwarmPolicy(
        W=3,
        T_enter=1.0,
        T_exit=0.2,
        K=2,
        trigger_metric="snr",
        snr_epsilon=1e-6,
        use_gap_gate=True,
        gap_enter_threshold=1.0,
        gap_window=1,
    )
    p = make_project(Mode.ASYNC, [0, 0, 0])
    p.signal_events_per_tick = [2, 2, 2]
    p.noise_events_per_tick = [0, 1, 0]
    p.gap_per_tick = [0.4]
    assert policy.step(p, t=8) is None

    p.gap_per_tick = [1.2]
    assert policy.step(p, t=9) == Mode.SYNC


def test_swarm_gap_gate_or_mode_enters_on_gap_even_if_signal_low():
    policy = SwarmPolicy(
        W=3,
        T_enter=5.0,  # intentionally high so signal alone won't trigger
        T_exit=0.2,
        K=2,
        trigger_metric="snr",
        snr_epsilon=1e-6,
        use_gap_gate=True,
        gap_gate_mode="or",
        gap_enter_threshold=1.0,
        gap_window=1,
    )
    p = make_project(Mode.ASYNC, [0, 0, 0])
    p.signal_events_per_tick = [1, 0, 1]
    p.noise_events_per_tick = [1, 1, 1]
    p.gap_per_tick = [1.2]
    assert policy.step(p, t=12) == Mode.SYNC


def test_swarm_cooldown_blocks_immediate_mode_flap() -> None:
    policy = SwarmPolicy(
        W=2,
        T_enter=1.0,
        T_exit=0.2,
        K=1,
        trigger_metric="snr",
        snr_epsilon=1e-6,
        cooldown_ticks=2,
    )
    p = make_project(Mode.ASYNC, [0, 0])
    p.signal_events_per_tick = [2, 2]
    p.noise_events_per_tick = [0, 0]
    assert policy.step(p, t=5) == Mode.SYNC

    p.mode = Mode.SYNC
    p.signal_events_per_tick.extend([0, 0])
    p.noise_events_per_tick.extend([3, 3])
    # Exit condition holds, but cooldown should block at t=6 and t=7.
    assert policy.step(p, t=6) is None
    assert policy.step(p, t=7) is None
    assert policy.step(p, t=8) == Mode.ASYNC


def test_periodic_sync_basic_schedule():
    policy = PeriodicSyncPolicy(period=4, sync_ticks=1)
    p = make_project(policy.initial_mode(), [])
    assert p.mode == Mode.SYNC

    # t=0 in SYNC window, t=1 leaves SYNC window.
    assert policy.step(p, t=0) is None
    assert policy.step(p, t=1) == Mode.ASYNC

    p.mode = Mode.ASYNC
    # t=4 starts next SYNC window.
    assert policy.step(p, t=4) == Mode.SYNC


def test_periodic_sync_stress_mapping_from_build_policy():
    cfg = {
        "type": "periodic_sync",
        "period": 20,
        "sync_ticks": 1,
        "stress_level": 3.0,
        "period_by_stress": {"1.0": 20, "3.0": 8},
        "sync_ticks_by_stress": {"1.0": 1, "3.0": 1},
    }
    policy = build_policy(cfg)
    assert isinstance(policy, PeriodicSyncPolicy)
    # At stress 3.0 mapped period should be 8, so t=7 still SYNC? No, only tick 0 in each period.
    p = make_project(policy.initial_mode(), [])
    assert p.mode == Mode.SYNC
    assert policy.step(p, t=1) == Mode.ASYNC
