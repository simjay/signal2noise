"""Async and Sync communication channel models."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AsyncChannel:
    """Asynchronous communication channel (e.g. Jira/Slack).

    Messages are queued and delivered on the next tick.  Low overhead
    but also low bandwidth — information may be incomplete.

    Attributes
    ----------
    lambda_cost:
        Cognitive-load cost per message sent (default 0.5 min equivalent).
    pending_messages:
        Messages queued for delivery next tick.
    total_messages_sent:
        Cumulative message count over the simulation run.
    """

    lambda_cost: float = 0.5

    pending_messages: list[dict] = field(default_factory=list, repr=False)
    total_messages_sent: int = 0

    def send(self, sender_id: str, recipient_id: str, content: str = "") -> None:
        """Queue a message for delivery on the next tick.

        Parameters
        ----------
        sender_id:
            Agent originating the message.
        recipient_id:
            Agent that will receive the message.
        content:
            Optional message payload (not semantically processed).
        """
        self.pending_messages.append(
            {"from": sender_id, "to": recipient_id, "content": content}
        )
        self.total_messages_sent += 1

    def deliver(self) -> list[dict]:
        """Deliver and clear queued messages.

        Returns
        -------
        list[dict]
            Messages delivered this tick.
        """
        delivered = list(self.pending_messages)
        self.pending_messages.clear()
        return delivered

    def coordination_cost(self, n_messages: int | None = None) -> float:
        """Compute total async coordination cost.

        Parameters
        ----------
        n_messages:
            Number of messages to cost; defaults to total_messages_sent.

        Returns
        -------
        float
            λ × message_count.
        """
        count = n_messages if n_messages is not None else self.total_messages_sent
        return self.lambda_cost * count


@dataclass
class SyncChannel:
    """Synchronous communication channel (e.g. Zoom/Huddle).

    Blocks all participants for the full session duration.  High
    bandwidth — full context is transferred — but incurs cognitive load.

    Attributes
    ----------
    error_reduction:
        Fractional reduction in rework defect probability when sync is
        active (default 0.4 → 40 % reduction).
    total_sync_ticks:
        Number of ticks the channel has been in active sync mode.
    active:
        Whether a sync session is currently in progress.
    """

    error_reduction: float = 0.4
    total_sync_ticks: int = 0
    active: bool = False

    def start_session(self) -> None:
        """Mark a sync session as started."""
        self.active = True

    def end_session(self) -> None:
        """Mark a sync session as ended."""
        self.active = False

    def record_tick(self) -> None:
        """Record that one tick of sync time has elapsed (call once per tick)."""
        if self.active:
            self.total_sync_ticks += 1

    def adjusted_error_rate(self, base_error_rate: float) -> float:
        """Return the effective error rate when this sync channel is active.

        Synchronous communication reduces defect probability during rework
        resolution by providing high-bandwidth context.

        Parameters
        ----------
        base_error_rate:
            Nominal error probability before sync adjustment.

        Returns
        -------
        float
            Adjusted error probability clamped to [0, 1].
        """
        return max(0.0, base_error_rate * (1.0 - self.error_reduction))
