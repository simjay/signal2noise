from __future__ import annotations

import copy
import csv
import json
from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore
except ModuleNotFoundError:
    yaml = None

from signal2noise.entities import Config


def _parse_scalar(token: str) -> Any:
    token = token.strip()
    if token == "":
        return ""
    low = token.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    if low in {"null", "none"}:
        return None
    if (token.startswith('"') and token.endswith('"')) or (token.startswith("'") and token.endswith("'")):
        return token[1:-1]
    try:
        return int(token)
    except ValueError:
        pass
    try:
        return float(token)
    except ValueError:
        pass
    return token


def _parse_inline_list(text: str) -> list[Any]:
    body = text.strip()[1:-1].strip()
    if not body:
        return []
    row = next(csv.reader([body], skipinitialspace=True))
    return [_parse_scalar(item) for item in row]


def _parse_simple_yaml(text: str) -> dict[str, Any]:
    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, root)]

    for raw_line in text.splitlines():
        if not raw_line.strip():
            continue
        line_no_comment = raw_line.split("#", 1)[0]
        if not line_no_comment.strip():
            continue

        indent = len(line_no_comment) - len(line_no_comment.lstrip(" "))
        line = line_no_comment.strip()
        if ":" not in line:
            raise RuntimeError(f"Unsupported YAML line: {raw_line}")

        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()

        while len(stack) > 1 and indent <= stack[-1][0]:
            stack.pop()
        current = stack[-1][1]

        if value == "":
            child: dict[str, Any] = {}
            current[key] = child
            stack.append((indent, child))
            continue

        if value.startswith("[") and value.endswith("]"):
            current[key] = _parse_inline_list(value)
        else:
            current[key] = _parse_scalar(value)

    return root


def load_config_file(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if p.suffix.lower() not in {".yaml", ".yml"}:
        raise RuntimeError("Only YAML config files are supported (.yaml/.yml).")
    if yaml is not None:
        return yaml.safe_load(text)
    return _parse_simple_yaml(text)


def save_json(path: str | Path, obj: dict[str, Any]) -> None:
    Path(path).write_text(json.dumps(obj, indent=2, sort_keys=True), encoding="utf-8")


def dict_to_config(cfg: dict[str, Any]) -> Config:
    merged = copy.deepcopy(cfg)
    defaults = Config()
    return Config(
        seed=int(merged.get("seed", defaults.seed)),
        n_runs=int(merged.get("n_runs", defaults.n_runs)),
        ticks_per_run=int(merged.get("ticks_per_run", defaults.ticks_per_run)),
        team_size=int(merged.get("team_size", defaults.team_size)),
        integration_check_interval=int(
            merged.get("integration_check_interval", defaults.integration_check_interval)
        ),
        rework_effort_fraction=float(
            merged.get("rework_effort_fraction", defaults.rework_effort_fraction)
        ),
        retest_effort_fraction=float(
            merged.get("retest_effort_fraction", defaults.retest_effort_fraction)
        ),
        task_graph=merged.get("task_graph", {}),
        task_effort_distribution=merged.get("task_effort_distribution", {}),
        agent_distributions=merged.get("agent_distributions", {}),
        propagation=merged.get("propagation", {}),
        mode_effects=merged.get("mode_effects", {}),
        policy=merged.get("policy", {}),
        costs=merged.get("costs", {}),
        metrics=merged.get("metrics", {}),
    )


def set_nested(cfg: dict[str, Any], dotted_key: str, value: Any) -> None:
    parts = dotted_key.split(".")
    cur = cfg
    for p in parts[:-1]:
        if p not in cur or not isinstance(cur[p], dict):
            cur[p] = {}
        cur = cur[p]
    cur[parts[-1]] = value
