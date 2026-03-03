"""Coordination protocols: async-only, sync-always, and adaptive."""

from signal2noise.protocols.adaptive import AdaptiveProtocol
from signal2noise.protocols.async_only import AsyncOnlyProtocol
from signal2noise.protocols.base import Protocol
from signal2noise.protocols.sync_always import SyncAlwaysProtocol

__all__ = [
    "AdaptiveProtocol",
    "AsyncOnlyProtocol",
    "Protocol",
    "SyncAlwaysProtocol",
]
