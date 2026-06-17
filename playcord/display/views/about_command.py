"""View rendering for the ``/about`` command response."""

from __future__ import annotations

import discord

from playcord.display.strife_ui import StrifeContainer, StrifeView
from playcord.display.views._layout import (
    append_blocks,
    link_button,
    nav_row,
    primary_button,
    secondary_button,
    text_block,
)
from playcord.infrastructure.constants import EPHEMERAL_DELETE_AFTER
from playcord.infrastructure.locale import get


async def _response_send_message(
    interaction: discord.Interaction,
    *args: object,
    **kwargs: object,
) -> discord.WebhookMessage:
    return await interaction.response.send_message(*args, **kwargs)  # type: ignore[arg-type]


class AboutView(StrifeView):
    """About page with external link buttons in the bottom action row."""

    def __init__(
        self,
        bot: discord.Client,
        user_id: int,
        guild_id: int,
        body_text: str,
        attributions_text: str,
    ) -> None:
        super().__init__(timeout=None)
        self.bot = bot
        self.user_id = user_id
        self.guild_id = guild_id
        self.body_text = body_text
        self.attributions_text = attributions_text

        container = StrifeContainer()
        body_text_clean = (body_text or "").strip()
        if body_text_clean:
            append_blocks(container, text_block(body_text_clean), has_content=False)
            container.add_item(discord.ui.Separator())
        github_url = get("brand.github_url")

        async def attributions_callback(interaction: discord.Interaction) -> None:
            if (
                interaction.user.id != self.user_id
                or interaction.guild_id != self.guild_id
            ):
                await _response_send_message(
                    interaction,
                    get("interactions.about_not_yours"),
                    ephemeral=True,
                    delete_after=EPHEMERAL_DELETE_AFTER,
                )
                return

            attributions_view = AttributionsView(
                bot=self.bot,
                user_id=self.user_id,
                guild_id=self.guild_id,
                body_text=self.body_text,
                attributions_text=self.attributions_text,
            )
            await interaction.response.edit_message(view=attributions_view)

        row = nav_row(
            link_button(
                label=get("buttons.about_github"),
                url=github_url,
                icon="github",
            ),
            link_button(
                label=get("buttons.about_docs"),
                url=get("brand.readme_url"),
            ),
            link_button(
                label=get("buttons.about_issues"),
                url=f"{github_url}/issues",
            ),
            primary_button(
                label=get("buttons.about_attributions"),
                icon="info",
                callback=attributions_callback,
            ),
        )
        container.add_item(row)
        self.add_item(container)


class AttributionsView(StrifeView):
    """Attributions page with a back button."""

    def __init__(
        self,
        bot: discord.Client,
        user_id: int,
        guild_id: int,
        body_text: str,
        attributions_text: str,
    ) -> None:
        super().__init__(timeout=None)
        self.bot = bot
        self.user_id = user_id
        self.guild_id = guild_id
        self.body_text = body_text
        self.attributions_text = attributions_text

        container = StrifeContainer()
        attributions_text_clean = (attributions_text or "").strip()
        if attributions_text_clean:
            append_blocks(
                container,
                text_block(attributions_text_clean),
                has_content=False,
            )
            container.add_item(discord.ui.Separator())

        async def back_callback(interaction: discord.Interaction) -> None:
            if (
                interaction.user.id != self.user_id
                or interaction.guild_id != self.guild_id
            ):
                await _response_send_message(
                    interaction,
                    get("interactions.about_not_yours"),
                    ephemeral=True,
                    delete_after=EPHEMERAL_DELETE_AFTER,
                )
                return

            about_view = AboutView(
                bot=self.bot,
                user_id=self.user_id,
                guild_id=self.guild_id,
                body_text=self.body_text,
                attributions_text=self.attributions_text,
            )
            await interaction.response.edit_message(view=about_view)

        row = nav_row(
            secondary_button(
                label=get("buttons.back"),
                icon="previous",
                callback=back_callback,
            ),
        )
        container.add_item(row)
        self.add_item(container)
