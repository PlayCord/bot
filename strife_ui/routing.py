"""Routing and validation system for strife_ui components."""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING, Any, ClassVar, Self

import discord

if TYPE_CHECKING:
    from strife_ui.routing import StrifeView

logger = logging.getLogger("strife_ui.routing")

MIN_SEGMENTS = 3
MIN_PARTS = 2


class StrifeRegistry:
    """In-memory registry of active Strife interaction sessions."""

    _active_sessions: ClassVar[set[str]] = set()

    @classmethod
    def register(cls, interaction_id: str) -> None:
        """Register a new interaction ID as active."""
        cls._active_sessions.add(interaction_id)
        logger.debug("Registered strife interaction: %s", interaction_id)

    @classmethod
    def unregister(cls, interaction_id: str) -> None:
        """Unregister an interaction ID."""
        cls._active_sessions.discard(interaction_id)
        logger.debug("Unregistered strife interaction: %s", interaction_id)

    @classmethod
    def is_active(cls, interaction_id: str) -> bool:
        """Check if a strife interaction session is currently active."""
        return interaction_id in cls._active_sessions


def generate_interaction_id(prefix: str = "strife") -> str:
    """Generate a unique interaction session identifier."""
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


async def handle_invalid_interaction(
    interaction: discord.Interaction, view: discord.ui.View
) -> None:
    """Disable view components, edit the message, and send an ephemeral error."""
    # Disable all walked components (supporting layout containers)
    for child in view.walk_children():
        if hasattr(child, "disabled"):
            child.disabled = True

    # Try to edit the message to show disabled state
    try:
        if not interaction.response.is_done():
            await interaction.response.edit_message(view=view)
        else:
            await interaction.message.edit(view=view)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Failed to edit message to disable components: %s", exc)

    # Inform the user ephemerally
    msg = (
        "This interaction is no longer valid "
        "(the session has expired or been replaced)."
    )
    try:
        if not interaction.response.is_done():
            await interaction.response.send_message(msg, ephemeral=True)
        else:
            await interaction.followup.send(msg, ephemeral=True)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Failed to send ephemeral invalidation message: %s", exc)


async def _disable_stale_message_on_interaction(
    interaction: discord.Interaction, message: discord.Message
) -> None:
    """Reconstruct and disable components on a stale message."""
    try:
        stale_view = discord.ui.View.from_message(message)
        for child in stale_view.walk_children():
            if hasattr(child, "disabled"):
                child.disabled = True

        if not interaction.response.is_done():
            await interaction.response.edit_message(view=stale_view)
        else:
            await message.edit(view=stale_view)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Failed to edit stale message: %s", exc)


async def _notify_stale_interaction(interaction: discord.Interaction) -> None:
    """Send ephemeral notification indicating stale interaction session."""
    msg = (
        "This interaction is no longer valid "
        "(the bot restarted or the session expired)."
    )
    try:
        if not interaction.response.is_done():
            await interaction.response.send_message(msg, ephemeral=True)
        else:
            await interaction.followup.send(msg, ephemeral=True)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Failed to send stale ephemeral notification: %s", exc)


async def check_strife_interaction(interaction: discord.Interaction) -> bool:
    """
    Check if a strife interaction is valid.

    If the interaction belongs to an expired session or the bot restarted:
    1. Reconstruct a disabled version of the view from the message
    2. Edit the message to show all buttons disabled
    3. Send an ephemeral reply explaining the expiration
    """
    if interaction.type != discord.InteractionType.component:
        return True

    custom_id = interaction.data.get("custom_id")
    if not custom_id or not isinstance(custom_id, str):
        return True

    if not custom_id.startswith("strife:"):
        return True

    parts = custom_id.split(":")
    if len(parts) < MIN_SEGMENTS:
        return True

    interaction_id = parts[-1]

    # If the interaction session is active, propagation continues
    if StrifeRegistry.is_active(interaction_id):
        return True

    message = interaction.message
    if message:
        await _disable_stale_message_on_interaction(interaction, message)

    await _notify_stale_interaction(interaction)
    return False


def setup_strife_middleware(bot: discord.Client) -> None:
    """
    Register the strife middleware onto the bot's on_interaction event.

    Wraps any existing on_interaction callback.
    """
    original_on_interaction = getattr(bot, "on_interaction", None)

    async def new_on_interaction(interaction: discord.Interaction) -> None:
        is_valid = await check_strife_interaction(interaction)
        if not is_valid:
            return  # Block propagation

        if original_on_interaction:
            await original_on_interaction(interaction)

    bot.on_interaction = new_on_interaction


class StrifeView(discord.ui.LayoutView):
    """Base View class that automatically routes and validates custom_ids."""

    def __init__(
        self,
        *args: Any,  # noqa: ANN401
        interaction_id: str | None = None,
        timeout: float | None = 180.0,
        **kwargs: Any,  # noqa: ANN401
    ) -> None:
        """Initialize a StrifeView with session validation routing."""
        super().__init__(*args, timeout=timeout, **kwargs)
        self.interaction_id = interaction_id or generate_interaction_id()
        StrifeRegistry.register(self.interaction_id)
        self._apply_routing_ids()

    def _apply_routing_ids(self) -> None:
        """Apply session-specific routing IDs to all child elements."""
        for child in self.walk_children():
            self._route_item(child)

    def _route_item(self, item: discord.ui.Item) -> None:
        if hasattr(item, "custom_id") and item.custom_id:
            cid = item.custom_id
            if self.interaction_id in cid:
                return

            original_id = cid
            if original_id.startswith("strife:"):
                parts = original_id.split(":")
                if len(parts) >= MIN_PARTS:
                    original_id = parts[1]

            item.custom_id = f"strife:{original_id}:{self.interaction_id}"

    def add_item(self, item: discord.ui.Item) -> Self:
        """Add a component item to the view and apply session routing ID."""
        super().add_item(item)
        self._apply_routing_ids()
        return self

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Check if interaction custom ID matches the session interaction ID."""
        custom_id = interaction.data.get("custom_id")
        if not custom_id or not isinstance(custom_id, str):
            return True

        if not custom_id.startswith("strife:"):
            return True

        parts = custom_id.split(":")
        if len(parts) < MIN_SEGMENTS:
            return True

        interaction_id = parts[-1]
        active = StrifeRegistry.is_active(interaction_id)
        if interaction_id != self.interaction_id or not active:
            await handle_invalid_interaction(interaction, self)
            return False

        return True

    def stop(self) -> None:
        """Stop listening to interactions and unregister session ID."""
        super().stop()
        StrifeRegistry.unregister(self.interaction_id)

    async def on_timeout(self) -> None:
        """Handle view timeout by stopping interactions."""
        self.stop()
