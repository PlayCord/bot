"""Opinionated Discord components with required emojis."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

import discord

from strife_ui.emojis import resolve_emoji, resolve_emoji_string

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence


class StrifeButton(discord.ui.Button):
    """A styled Button that requires an emoji."""

    def __init__(  # noqa: PLR0913
        self,
        *,
        label: str,
        emoji: str | int | discord.Emoji | discord.PartialEmoji,
        style: discord.ButtonStyle = discord.ButtonStyle.secondary,
        custom_id: str | None = None,
        disabled: bool = False,
        callback: Callable[[discord.Interaction], Any] | None = None,
        **kwargs: Any,  # noqa: ANN401
    ) -> None:
        """
        Initialize a StrifeButton.

        Raises:
            ValueError: If no emoji is provided.

        """
        # Enforce emoji requirement
        if not emoji:
            err_msg = "Every button in strife_ui must have an emoji."
            raise ValueError(err_msg)

        resolved_emoji = resolve_emoji(emoji)

        # Generate custom_id if not a link button to ensure strife routing works
        if style != discord.ButtonStyle.link and not custom_id:
            custom_id = f"btn_{uuid.uuid4().hex[:8]}"

        super().__init__(
            label=label,
            style=style,
            custom_id=custom_id,
            emoji=resolved_emoji,
            disabled=disabled,
            **kwargs,
        )
        self._user_callback = callback

    async def callback(self, interaction: discord.Interaction) -> None:
        """Handle button click interaction."""
        if self._user_callback:
            await self._user_callback(interaction)


class StrifeSelectOption:
    """Dataclass representing a standard option in a StrifeDropdown."""

    def __init__(
        self,
        label: str,
        value: str,
        emoji: str | int | discord.Emoji | discord.PartialEmoji,
        description: str | None = None,
        *,
        default: bool = False,
    ) -> None:
        """
        Initialize a StrifeSelectOption.

        Raises:
            ValueError: If no emoji is provided.

        """
        if not emoji:
            err_msg = f"Select option {label!r} must have an emoji."
            raise ValueError(err_msg)
        self.label = label
        self.value = value
        self.emoji = emoji
        self.description = description
        self.default = default


class StrifeSelectCategory:
    """Dataclass representing an unselectable category header in a StrifeDropdown."""

    def __init__(self, title: str) -> None:
        """Initialize a StrifeSelectCategory."""
        self.title = title.upper()


class StrifeDropdown(discord.ui.Select):
    """A styled Select Menu that supports categories and required emojis."""

    def __init__(  # noqa: PLR0913
        self,
        *,
        description: str,
        options: Sequence[StrifeSelectOption | StrifeSelectCategory],
        placeholder: str = "Select an option...",
        emoji: str | int | discord.Emoji | discord.PartialEmoji | None = None,
        custom_id: str | None = None,
        min_values: int = 1,
        max_values: int = 1,
        disabled: bool = False,
        callback: Callable[[discord.Interaction, str], Any] | None = None,
        **kwargs: Any,  # noqa: ANN401
    ) -> None:
        """
        Initialize a StrifeDropdown.

        Raises:
            ValueError: If options list is empty.
            TypeError: If an option is of an invalid type.

        """
        self.description_text = description.strip()
        self._user_callback = callback
        self._headers: set[str] = set()

        if not options:
            err_opt = "StrifeDropdown must contain at least one option."
            raise ValueError(err_opt)

        discord_options: list[discord.SelectOption] = []
        for idx, opt in enumerate(options):
            if isinstance(opt, StrifeSelectCategory):
                header_val = f"header_{idx}_{uuid.uuid4().hex[:6]}"
                self._headers.add(header_val)
                discord_options.append(
                    discord.SelectOption(
                        label="\u200b",
                        value=header_val,
                        description=opt.title,
                    )
                )
            elif isinstance(opt, StrifeSelectOption):
                discord_options.append(
                    discord.SelectOption(
                        label=opt.label,
                        value=opt.value,
                        emoji=resolve_emoji(opt.emoji),
                        description=opt.description,
                        default=opt.default,
                    )
                )
            else:
                err_type = (
                    "Options must be StrifeSelectOption or "
                    f"StrifeSelectCategory, got {type(opt)}"
                )
                raise TypeError(err_type)

        if emoji:
            emoji_str = resolve_emoji_string(emoji)
            placeholder = f"{emoji_str} {placeholder}"

        if not custom_id:
            custom_id = f"sel_{uuid.uuid4().hex[:8]}"

        super().__init__(
            placeholder=placeholder,
            min_values=min_values,
            max_values=max_values,
            options=discord_options,
            disabled=disabled,
            custom_id=custom_id,
            **kwargs,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        """Handle dropdown option selection."""
        selected_value = self.values[0] if self.values else None
        if selected_value in self._headers:
            # It's an unselectable header! Defer and reset component focus
            await interaction.response.defer()
            if self.view:
                await interaction.edit_original_response(view=self.view)
            return

        await self.on_select(interaction, selected_value)

    async def on_select(self, interaction: discord.Interaction, value: str) -> None:
        """Handle valid option selections. Subclasses can override this."""
        if self._user_callback:
            await self._user_callback(interaction, value)
