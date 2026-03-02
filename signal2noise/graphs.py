from __future__ import annotations

import random
from collections import defaultdict
from pathlib import Path
from typing import Any


def _ensure_acyclic(n_tasks: int, edges: list[tuple[int, int]]) -> None:
    graph = defaultdict(list)
    indeg = [0] * n_tasks
    for u, v in edges:
        graph[u].append(v)
        indeg[v] += 1

    queue = [i for i in range(n_tasks) if indeg[i] == 0]
    seen = 0
    while queue:
        u = queue.pop()
        seen += 1
        for v in graph[u]:
            indeg[v] -= 1
            if indeg[v] == 0:
                queue.append(v)
    if seen != n_tasks:
        raise ValueError("Generated graph is not acyclic")


def generate_graph(task_graph_cfg: dict[str, Any], rng: random.Random) -> dict[str, Any]:
    gtype = str(task_graph_cfg.get("type", "random_dag"))
    n_tasks = int(task_graph_cfg.get("n_tasks", 12))

    if gtype == "chain":
        edges = [(i, i + 1) for i in range(n_tasks - 1)]
    elif gtype == "dag" or gtype == "random_dag":
        edge_prob = float(task_graph_cfg.get("edge_prob", 0.2))
        max_in_degree = int(task_graph_cfg.get("max_in_degree", max(1, n_tasks // 3)))
        edges = []
        for u in range(n_tasks):
            for v in range(u + 1, n_tasks):
                if rng.random() < edge_prob:
                    edges.append((u, v))
        if max_in_degree > 0:
            indeg_count: dict[int, int] = {}
            filtered = []
            for u, v in sorted(edges, key=lambda x: (x[1], x[0])):
                current = indeg_count.get(v, 0)
                if current >= max_in_degree:
                    continue
                filtered.append((u, v))
                indeg_count[v] = current + 1
            edges = filtered
    elif gtype == "loaded_file":
        path = Path(str(task_graph_cfg["path"]))
        if not path.exists():
            raise FileNotFoundError(f"Graph file not found: {path}")
        data: dict[str, Any]
        if path.suffix.lower() == ".json":
            import json

            data = json.loads(path.read_text(encoding="utf-8"))
        else:
            try:
                import yaml  # type: ignore
            except ModuleNotFoundError as exc:
                raise RuntimeError(
                    "YAML graph file requested but PyYAML is not installed. "
                    "Use JSON graph files or install PyYAML."
                ) from exc

            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        n_tasks = int(data.get("n_tasks", n_tasks))
        edges = [tuple(e) for e in data.get("edges", [])]
    else:
        raise ValueError(f"Unsupported task graph type: {gtype}")

    _ensure_acyclic(n_tasks, edges)

    deps = {f"T{i}": [] for i in range(n_tasks)}
    dependents = {f"T{i}": [] for i in range(n_tasks)}
    for u, v in edges:
        deps[f"T{v}"].append(f"T{u}")
        dependents[f"T{u}"].append(f"T{v}")

    return {
        "n_tasks": n_tasks,
        "edges": edges,
        "deps": deps,
        "dependents": dependents,
    }


def assign_couplings(
    edges: list[tuple[int, int]],
    coupling_cfg: dict[str, Any],
    rng: random.Random,
) -> dict[tuple[str, str], float]:
    if "coupling_strength" in coupling_cfg:
        fixed = float(coupling_cfg["coupling_strength"])
        return {(f"T{u}", f"T{v}"): fixed for u, v in edges}

    dist = coupling_cfg.get("coupling_distribution", {"kind": "uniform", "low": 0.3, "high": 0.8})
    kind = str(dist.get("kind", "uniform"))

    result: dict[tuple[str, str], float] = {}
    for u, v in edges:
        if kind == "uniform":
            low = float(dist.get("low", 0.3))
            high = float(dist.get("high", 0.8))
            c = float(rng.uniform(low, high))
        elif kind == "fixed":
            c = float(dist.get("value", 0.6))
        elif kind == "beta":
            a = float(dist.get("a", 2.0))
            b = float(dist.get("b", 2.0))
            c = float(rng.betavariate(a, b))
        else:
            raise ValueError(f"Unsupported coupling distribution: {kind}")
        result[(f"T{u}", f"T{v}")] = max(0.0, min(1.0, c))
    return result
