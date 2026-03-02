from __future__ import annotations

import random
from collections import defaultdict, deque

from signal2noise.graphs import generate_graph


def is_acyclic(n: int, edges: list[tuple[int, int]]) -> bool:
    g = defaultdict(list)
    indeg = [0] * n
    for u, v in edges:
        g[u].append(v)
        indeg[v] += 1
    q = deque([i for i in range(n) if indeg[i] == 0])
    seen = 0
    while q:
        u = q.popleft()
        seen += 1
        for v in g[u]:
            indeg[v] -= 1
            if indeg[v] == 0:
                q.append(v)
    return seen == n


def test_random_dag_is_acyclic_and_consistent():
    rng = random.Random(123)
    graph = generate_graph(
        {"type": "random_dag", "n_tasks": 25, "edge_prob": 0.2, "max_in_degree": 4},
        rng,
    )

    assert is_acyclic(graph["n_tasks"], graph["edges"])

    for u, v in graph["edges"]:
        assert f"T{u}" in graph["deps"][f"T{v}"]
        assert f"T{v}" in graph["dependents"][f"T{u}"]
