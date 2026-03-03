"""Tests for signal2noise.core.agent."""

from __future__ import annotations

from signal2noise.core.agent import Agent
from signal2noise.core.types import AgentState

def test_agent_default_state():
    agent = Agent(id="A0", skill_level=0.5)
    assert agent.cognitive_load == 0.0
    assert agent.state == AgentState.IDLE
    assert agent.position == 0

def test_apply_allocation_work_dominant():
    agent = Agent(id="A0", skill_level=0.8)
    agent.apply_allocation(0.85, 0.0, 0.15)
    assert agent.state == AgentState.WORKING
    assert abs(agent.work_fraction - 0.85) < 1e-9
    assert abs(agent.sync_fraction - 0.0) < 1e-9

def test_apply_allocation_sync_dominant():
    agent = Agent(id="A0", skill_level=0.8)
    agent.apply_allocation(0.2, 0.5, 0.3)
    assert agent.state == AgentState.IN_SYNC
    # Fractions should be normalised
    total = agent.work_fraction + agent.sync_fraction + agent.async_fraction
    assert abs(total - 1.0) < 1e-9

def test_apply_allocation_async_dominant():
    agent = Agent(id="A0", skill_level=0.6)
    agent.apply_allocation(0.3, 0.0, 0.7)
    assert agent.state == AgentState.READING_ASYNC

def test_apply_allocation_all_zero_defaults_to_working():
    agent = Agent(id="A0", skill_level=0.5)
    agent.apply_allocation(0.0, 0.0, 0.0)
    assert agent.work_fraction == 1.0
    assert agent.sync_fraction == 0.0
    assert agent.async_fraction == 0.0

def test_effective_error_rate_clamps_to_unit():
    # Very high complexity, very low skill — result should not exceed 1.0
    agent = Agent(id="A0", skill_level=0.01, cognitive_load=1.0)
    p = agent.effective_error_rate(task_complexity=1.0, base_error_rate=1.0, cognitive_load_penalty=1.0)
    assert 0.0 <= p <= 1.0

def test_effective_error_rate_zero_complexity():
    agent = Agent(id="A0", skill_level=0.5, cognitive_load=0.0)
    p = agent.effective_error_rate(task_complexity=0.0)
    assert p == 0.0

def test_effective_error_rate_increases_with_load():
    agent = Agent(id="A0", skill_level=0.6)
    agent.cognitive_load = 0.0
    p_low = agent.effective_error_rate(0.5)
    agent.cognitive_load = 1.0
    p_high = agent.effective_error_rate(0.5)
    assert p_high > p_low

def test_effective_error_rate_decreases_with_skill():
    a_low = Agent(id="A0", skill_level=0.2)
    a_high = Agent(id="A1", skill_level=0.9)
    p_low = a_low.effective_error_rate(0.5)
    p_high = a_high.effective_error_rate(0.5)
    assert p_high < p_low
