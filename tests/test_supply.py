"""Tests for signal2noise.supply.allocator and signal2noise.supply.cognitive_load."""

from __future__ import annotations

from signal2noise.core.agent import Agent
from signal2noise.core.types import AgentState
from signal2noise.supply.allocator import Allocator
from signal2noise.supply.cognitive_load import CognitiveLoadModel

# ---------------------------------------------------------------------------
# Allocator tests
# ---------------------------------------------------------------------------

def _agents(n: int = 3) -> list[Agent]:
    return [Agent(id=f"A{i}", skill_level=0.5 + 0.1 * i) for i in range(n)]

def test_allocator_applies_policy():
    agents = _agents(2)
    # A0: work dominant (0.8 > 0.0, 0.2) → WORKING
    # A1: sync dominant (0.7 > 0.1, 0.2) → IN_SYNC
    policy = {"A0": (0.8, 0.0, 0.2), "A1": (0.1, 0.7, 0.2)}
    Allocator().apply(agents, policy)
    assert agents[0].state == AgentState.WORKING
    assert agents[1].state == AgentState.IN_SYNC

def test_allocator_defaults_to_working_for_missing_agents():
    agents = _agents(2)
    policy = {"A0": (0.7, 0.0, 0.3)}
    Allocator().apply(agents, policy)
    # A1 not in policy → default (1, 0, 0)
    assert agents[1].work_fraction == 1.0
    assert agents[1].sync_fraction == 0.0

def test_allocator_fractions_sum_to_one():
    agents = _agents(1)
    policy = {"A0": (2.0, 1.0, 1.0)}  # unnormalised
    Allocator().apply(agents, policy)
    a = agents[0]
    total = a.work_fraction + a.sync_fraction + a.async_fraction
    assert abs(total - 1.0) < 1e-9

def test_allocator_all_sync_policy():
    agents = _agents(3)
    policy = {a.id: (0.0, 1.0, 0.0) for a in agents}
    Allocator().apply(agents, policy)
    for a in agents:
        assert a.state == AgentState.IN_SYNC

def test_allocator_all_async_policy():
    agents = _agents(3)
    policy = {a.id: (0.0, 0.0, 1.0) for a in agents}
    Allocator().apply(agents, policy)
    for a in agents:
        assert a.state == AgentState.READING_ASYNC

# ---------------------------------------------------------------------------
# CognitiveLoadModel tests
# ---------------------------------------------------------------------------

def test_cognitive_load_increases_during_sync():
    model = CognitiveLoadModel(sync_load_rate=0.2, async_load_rate=0.0, recovery_rate=0.0, natural_decay=0.0)
    agent = Agent(id="A0", skill_level=0.5, cognitive_load=0.0)
    agent.apply_allocation(0.0, 1.0, 0.0)  # all sync
    model.update([agent])
    assert agent.cognitive_load > 0.0

def test_cognitive_load_increases_during_async():
    model = CognitiveLoadModel(sync_load_rate=0.0, async_load_rate=0.1, recovery_rate=0.0, natural_decay=0.0)
    agent = Agent(id="A0", skill_level=0.5, cognitive_load=0.0)
    agent.apply_allocation(0.0, 0.0, 1.0)  # all async
    model.update([agent])
    assert agent.cognitive_load > 0.0

def test_cognitive_load_decreases_during_focused_work():
    model = CognitiveLoadModel(sync_load_rate=0.0, async_load_rate=0.0, recovery_rate=0.1, natural_decay=0.0)
    agent = Agent(id="A0", skill_level=0.5, cognitive_load=0.5)
    agent.apply_allocation(1.0, 0.0, 0.0)  # all work
    model.update([agent])
    assert agent.cognitive_load < 0.5

def test_cognitive_load_natural_decay():
    model = CognitiveLoadModel(sync_load_rate=0.0, async_load_rate=0.0, recovery_rate=0.0, natural_decay=0.05)
    agent = Agent(id="A0", skill_level=0.5, cognitive_load=0.3)
    agent.apply_allocation(0.0, 0.0, 0.0)  # idle
    model.update([agent])
    assert agent.cognitive_load < 0.3

def test_cognitive_load_clamped_to_unit():
    model = CognitiveLoadModel(sync_load_rate=1.0, async_load_rate=0.0, recovery_rate=0.0, natural_decay=0.0)
    agent = Agent(id="A0", skill_level=0.5, cognitive_load=0.95)
    agent.apply_allocation(0.0, 1.0, 0.0)  # all sync
    model.update([agent])
    assert agent.cognitive_load <= 1.0

def test_cognitive_load_clamped_to_zero():
    model = CognitiveLoadModel(sync_load_rate=0.0, async_load_rate=0.0, recovery_rate=1.0, natural_decay=1.0)
    agent = Agent(id="A0", skill_level=0.5, cognitive_load=0.01)
    agent.apply_allocation(1.0, 0.0, 0.0)  # all work
    model.update([agent])
    assert agent.cognitive_load >= 0.0

def test_sync_load_rate_higher_than_async():
    model = CognitiveLoadModel(sync_load_rate=0.15, async_load_rate=0.05, recovery_rate=0.0, natural_decay=0.0)
    a_sync = Agent(id="A0", skill_level=0.5, cognitive_load=0.0)
    a_async = Agent(id="A1", skill_level=0.5, cognitive_load=0.0)
    a_sync.apply_allocation(0.0, 1.0, 0.0)
    a_async.apply_allocation(0.0, 0.0, 1.0)
    model.update([a_sync, a_async])
    assert a_sync.cognitive_load > a_async.cognitive_load
