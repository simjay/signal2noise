"""Tests for signal2noise.protocols.*"""

from __future__ import annotations

import pytest

from signal2noise.core.agent import Agent
from signal2noise.protocols.adaptive import AdaptiveProtocol
from signal2noise.protocols.async_only import AsyncOnlyProtocol
from signal2noise.protocols.base import Protocol
from signal2noise.protocols.sync_always import SyncAlwaysProtocol

def _agents(n: int = 3) -> list[Agent]:
    return [Agent(id=f"A{i}", skill_level=0.6) for i in range(n)]

# ---------------------------------------------------------------------------
# AsyncOnlyProtocol
# ---------------------------------------------------------------------------

def test_async_only_name():
    assert AsyncOnlyProtocol().name() == "async_only"

def test_async_only_sync_fraction_always_zero():
    proto = AsyncOnlyProtocol()
    agents = _agents(3)
    policy = proto.decide(rework_rate=0.9, agents=agents, tick=0)
    for agent in agents:
        _, s, _ = policy[agent.id]
        assert s == 0.0

def test_async_only_work_fraction_positive():
    proto = AsyncOnlyProtocol()
    agents = _agents(3)
    policy = proto.decide(rework_rate=0.0, agents=agents, tick=0)
    for agent in agents:
        w, _, _ = policy[agent.id]
        assert w > 0.0

def test_async_only_fractions_sum_to_one():
    proto = AsyncOnlyProtocol()
    agents = _agents(2)
    policy = proto.decide(0.0, agents, 0)
    for a in agents:
        w, s, x = policy[a.id]
        assert abs(w + s + x - 1.0) < 1e-9

def test_async_only_is_protocol_subclass():
    assert isinstance(AsyncOnlyProtocol(), Protocol)

# ---------------------------------------------------------------------------
# SyncAlwaysProtocol
# ---------------------------------------------------------------------------

def test_sync_always_name():
    assert SyncAlwaysProtocol().name() == "sync_always"

def test_sync_always_sync_fraction_ge_s_min():
    proto = SyncAlwaysProtocol(s_min=0.2)
    agents = _agents(3)
    policy = proto.decide(rework_rate=0.0, agents=agents, tick=0)
    for a in agents:
        _, s, _ = policy[a.id]
        assert s >= proto.s_min - 1e-9

def test_sync_always_fractions_sum_to_one():
    proto = SyncAlwaysProtocol(s_min=0.25)
    agents = _agents(2)
    policy = proto.decide(0.0, agents, 0)
    for a in agents:
        w, s, x = policy[a.id]
        assert abs(w + s + x - 1.0) < 1e-9

def test_sync_always_s_min_clamp():
    # s_min > 1.0 should be clamped to 1.0
    proto = SyncAlwaysProtocol(s_min=2.0)
    assert proto.s_min == 1.0

def test_sync_always_is_protocol_subclass():
    assert isinstance(SyncAlwaysProtocol(), Protocol)

# ---------------------------------------------------------------------------
# AdaptiveProtocol
# ---------------------------------------------------------------------------

def test_adaptive_name():
    assert AdaptiveProtocol().name() == "adaptive"

def test_adaptive_is_protocol_subclass():
    assert isinstance(AdaptiveProtocol(), Protocol)

def test_adaptive_valve_closed_below_tau():
    proto = AdaptiveProtocol(tau=0.3)
    agents = _agents(2)
    policy = proto.decide(rework_rate=0.1, agents=agents, tick=0)
    # Valve should remain closed → sync fraction = 0
    for a in agents:
        _, s, _ = policy[a.id]
        assert s == 0.0
    assert not proto.valve_open

def test_adaptive_valve_opens_above_tau():
    proto = AdaptiveProtocol(tau=0.3, s_sync=0.3)
    agents = _agents(2)
    policy = proto.decide(rework_rate=0.5, agents=agents, tick=0)
    # Valve should open → sync fraction == s_sync
    for a in agents:
        _, s, _ = policy[a.id]
        assert abs(s - 0.3) < 1e-9
    assert proto.valve_open

def test_adaptive_valve_closes_after_rework_resolved():
    proto = AdaptiveProtocol(tau=0.3, exit_ratio=0.5, s_sync=0.3)
    agents = _agents(2)
    # Open valve
    proto.decide(rework_rate=0.5, agents=agents, tick=0)
    assert proto.valve_open
    # Rework rate drops well below exit threshold (0.3 × 0.5 = 0.15)
    proto.decide(rework_rate=0.05, agents=agents, tick=1)
    assert not proto.valve_open

def test_adaptive_hysteresis_stays_open_between_thresholds():
    """Valve should remain open when R(t) is between exit and enter thresholds."""
    proto = AdaptiveProtocol(tau=0.3, exit_ratio=0.5)
    agents = _agents(2)
    # Open valve
    proto.decide(rework_rate=0.5, agents=agents, tick=0)
    # R(t) = 0.2 is above exit threshold (0.15) but below enter threshold (0.3)
    proto.decide(rework_rate=0.2, agents=agents, tick=1)
    assert proto.valve_open

def test_adaptive_fractions_sum_to_one_both_modes():
    proto = AdaptiveProtocol(tau=0.3)
    agents = _agents(2)
    # Async mode
    policy_async = proto.decide(rework_rate=0.0, agents=agents, tick=0)
    for a in agents:
        w, s, x = policy_async[a.id]
        assert abs(w + s + x - 1.0) < 1e-9
    # Sync mode
    policy_sync = proto.decide(rework_rate=1.0, agents=agents, tick=1)
    for a in agents:
        w, s, x = policy_sync[a.id]
        assert abs(w + s + x - 1.0) < 1e-9
