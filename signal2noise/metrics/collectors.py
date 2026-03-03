"""TickSnapshot collector: hooks into the simulation loop each tick."""

from __future__ import annotations

from signal2noise.core.types import TickSnapshot


class TickCollector:
    """Collects per-tick state snapshots during a simulation run.

    Each call to ``record`` appends a ``TickSnapshot`` to the internal list.
    After the simulation completes, the ``snapshots`` list can be passed to
    the ``summary`` module for aggregation.
    """

    def __init__(self) -> None:
        self._snapshots: list[TickSnapshot] = []

    def record(self, snapshot: TickSnapshot) -> None:
        """Append a snapshot for the current tick.

        Parameters
        ----------
        snapshot:
            Complete state snapshot for one simulation tick.
        """
        self._snapshots.append(snapshot)

    @property
    def snapshots(self) -> list[TickSnapshot]:
        """Return the list of recorded snapshots (read-only view)."""
        return list(self._snapshots)

    def __len__(self) -> int:
        return len(self._snapshots)
