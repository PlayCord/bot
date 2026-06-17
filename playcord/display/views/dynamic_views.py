"""Dynamic and auxiliary LayoutViews from main layout_discord."""

from __future__ import annotations

import discord

from playcord.display.strife_ui import StrifeContainer, StrifeView
from playcord.display.views._layout import (
    append_blocks,
    button_row,
    icon_for_button,
    media_block,
    primary_button,
    resolve_button_emoji,
    secondary_button,
    summary_text_block,
    text_sections_block,
    title_block,
)
from playcord.infrastructure.constants import (
    BUTTON_PREFIX_REMATCH,
    EPHEMERAL_DELETE_AFTER,
)
from playcord.infrastructure.locale import get


async def _noop_button_interaction(interaction: discord.Interaction) -> None:
    """Placeholder callback for decorative buttons (e.g. link row)."""


class DynamicButtonView(discord.ui.LayoutView):
    """Dynamic button view built from declarative button dictionaries."""

    def __init__(
        self,
        buttons: list[dict],
        summary_text: str | None = None,
        text_sections: list[str] | None = None,
        table_image_url: str | None = None,
    ) -> None:
        super().__init__(timeout=None)
        container = StrifeContainer()
        has_content = False
        if text_sections:
            has_content = append_blocks(
                container,
                text_sections_block(text_sections),
                has_content=has_content,
            )
        elif summary_text:
            has_content = append_blocks(
                container,
                summary_text_block(summary_text),
                has_content=has_content,
            )
        if table_image_url:
            if has_content:
                container.add_item(discord.ui.Separator())
            append_blocks(container, media_block(table_image_url), has_content=False)
            has_content = True
        if has_content:
            container.add_item(discord.ui.Separator())

        row = discord.ui.ActionRow()
        count = 0
        for button in buttons:
            for argument in ["label", "style", "id", "disabled", "callback", "link"]:
                if argument not in button:
                    if argument == "disabled":
                        button[argument] = False
                        continue
                    button[argument] = None

            emoji_val = None
            if button.get("emoji"):
                emoji_val = resolve_button_emoji(button["emoji"])
            elif button.get("icon"):
                emoji_val = icon_for_button(button["icon"])

            item = discord.ui.Button(
                label=button["label"] if button["label"] is not None else "\u200b",
                style=button["style"],
                custom_id=button["id"],
                disabled=button["disabled"],
                url=button["link"],
                emoji=emoji_val,
            )
            if button["callback"] is None:
                item.callback = self._fail_callback
            elif button["callback"] == "none":
                item.callback = _noop_button_interaction
            else:
                item.callback = button["callback"]
            row.add_item(item)
            count += 1
            if count == 5:
                container.add_item(row)
                row = discord.ui.ActionRow()
                count = 0
        if count:
            container.add_item(row)
        self.add_item(container)

    async def _fail_callback(self, interaction: discord.Interaction) -> None:
        for child in self.walk_children():
            if hasattr(child, "disabled"):
                child.disabled = True

        await interaction.response.edit_message(view=self)

        await interaction.followup.send(
            content=get("interactions.dead_view"),
            ephemeral=True,
            delete_after=EPHEMERAL_DELETE_AFTER,
        )


class SpectateView(DynamicButtonView):
    """View for status message."""

    def __init__(
        self,
        spectate_button_id: str | None = None,
        peek_button_id: str | None = None,
        game_link: str | None = None,
        summary_text: str | None = None,
        table_image_url: str | None = None,
    ) -> None:
        buttons = [
            {
                "label": get("buttons.spectate"),
                "style": discord.ButtonStyle.primary,
                "id": spectate_button_id,
                "callback": "none",
                "icon": "spectate",
            },
        ]
        if peek_button_id:
            buttons.append(
                {
                    "label": get("buttons.peek"),
                    "style": discord.ButtonStyle.secondary,
                    "id": peek_button_id,
                    "callback": "none",
                    "icon": "peek",
                },
            )
        buttons.append(
            {
                "label": get("buttons.go_to_game"),
                "style": discord.ButtonStyle.link,
                "link": game_link,
                "icon": "external_link",
            },
        )
        super().__init__(
            buttons,
            summary_text=summary_text,
            table_image_url=table_image_url,
        )


class RematchView(DynamicButtonView):
    r"""Rematch button; interaction is handled in GamesCog (see callback \"none\")."""

    def __init__(self, match_id: int, summary_text: str | None = None) -> None:
        super().__init__(
            [
                {
                    "label": get("buttons.rematch"),
                    "style": discord.ButtonStyle.primary,
                    "id": f"{BUTTON_PREFIX_REMATCH}{match_id}",
                    "disabled": False,
                    "callback": "none",
                    "icon": "rematch",
                },
            ],
            summary_text=summary_text,
        )


class QuickActionsView(StrifeView):
    """Quick action buttons for profile, leaderboard, and other embeds."""

    def __init__(
        self,
        show_catalog: bool = True,
        show_help: bool = True,
        timeout: int = 180,
    ) -> None:
        super().__init__(timeout=timeout)
        container = StrifeContainer()
        action_buttons: list[discord.ui.Button] = []
        if show_catalog:
            catalog_btn = primary_button(
                label=get("buttons.view_catalog"),
                custom_id="quick_catalog",
                icon="catalog",
            )
            action_buttons.append(catalog_btn)

        if show_help:
            help_btn = secondary_button(
                label=get("buttons.get_help"),
                custom_id="quick_help",
                icon="about",
            )
            action_buttons.append(help_btn)

        append_blocks(
            container,
            title_block("Quick Actions", icon_key="playcord"),
            has_content=False,
        )
        if action_buttons:
            append_blocks(container, button_row(*action_buttons), has_content=True)
        self.add_item(container)
