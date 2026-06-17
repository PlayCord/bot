"""View rendering for the ``/catalog`` command response."""

from __future__ import annotations

import discord

from playcord.display.strife_ui import (
    StrifeContainer,
    StrifeDropdown,
    StrifePageScrubModal,
    StrifeSelectCategory,
    StrifeSelectOption,
    StrifeView,
    build_pagination_row,
    resolve_emoji_string,
)
from playcord.display.views._layout import (
    append_blocks,
    get_game_emoji,
    summary_text_block,
)
from playcord.infrastructure.constants import EPHEMERAL_DELETE_AFTER, NAME
from playcord.infrastructure.locale import fmt, get


async def _response_send_message(
    interaction: discord.Interaction,
    *args: object,
    **kwargs: object,
) -> discord.WebhookMessage:
    return await interaction.response.send_message(*args, **kwargs)  # type: ignore[arg-type]


def _meta_supports_roles(meta: dict) -> bool:
    if meta.get("supports_role_selection") or meta.get("supports_roles"):
        return True
    game_class = meta.get("class")
    if game_class is None:
        return False
    md = game_class.metadata
    role_mode = getattr(md, "role_mode", None)
    role_flow = getattr(md, "role_flow", None)
    if role_mode is not None and str(role_mode).lower() not in {"none", ""}:
        return True
    if role_flow is not None and str(role_flow).lower() not in {"none", ""}:
        return True
    return bool(getattr(md, "player_roles", None))


def _format_player_count(meta: dict) -> str:
    if meta.get("player_count_str"):
        return str(meta["player_count_str"])
    game_class = meta.get("class")
    if game_class is None:
        return "?"
    allowed = game_class.metadata.player_count
    if isinstance(allowed, int):
        return f"{allowed}p"
    if isinstance(allowed, tuple):
        return f"{min(allowed)}-{max(allowed)}p"
    return str(allowed)


class CatalogView(StrifeView):
    """Board game themed visual catalog view with filter dropdown and pagination."""

    def __init__(
        self,
        guild_id: int,
        user_id: int,
        all_games: list[str],
        game_metadata: dict[str, dict],
        games_per_page: int,
        current_page: int = 1,
        active_filter: str | None = None,
    ) -> None:
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.user_id = user_id
        self.all_games = all_games
        self.game_metadata = game_metadata
        self.games_per_page = games_per_page
        self.active_filter = active_filter
        self.current_page = current_page
        self.max_pages = 1
        self.body_text = ""

        self.rebuild_layout()

    def _validate_interaction(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            return False
        return interaction.guild_id == self.guild_id

    def rebuild_layout(self) -> None:
        self.clear_items()

        filtered_games: list[str] = []
        if self.active_filter and self.active_filter.startswith("tag:"):
            target_tag = self.active_filter[len("tag:") :]
            filtered_games = [
                g
                for g in self.all_games
                if target_tag in self.game_metadata[g].get("tags", ())
            ]
        elif self.active_filter and self.active_filter.startswith("support:"):
            target_support = self.active_filter[len("support:") :]
            if target_support == "Bots":
                filtered_games = [
                    g
                    for g in self.all_games
                    if self.game_metadata[g].get("supports_bots")
                ]
            elif target_support == "Roles":
                filtered_games = [
                    g
                    for g in self.all_games
                    if _meta_supports_roles(self.game_metadata[g])
                ]
            elif target_support == "Replays":
                filtered_games = [
                    g
                    for g in self.all_games
                    if self.game_metadata[g].get("supports_replays")
                ]
            elif target_support == "Lobby Options":
                filtered_games = [
                    g
                    for g in self.all_games
                    if self.game_metadata[g].get("supports_lobby_options")
                ]
            else:
                filtered_games = self.all_games
        else:
            filtered_games = self.all_games

        display_games = sorted(
            filtered_games,
            key=lambda gid: self.game_metadata[gid]["name"],
        )

        total_games = len(display_games)
        self.max_pages = max(
            1,
            (total_games + self.games_per_page - 1) // self.games_per_page,
        )
        self.current_page = max(1, min(self.current_page, self.max_pages))

        start_idx = (self.current_page - 1) * self.games_per_page
        end_idx = start_idx + self.games_per_page
        page_games = display_games[start_idx:end_idx]

        next_icon = resolve_emoji_string("forward")
        if self.active_filter:
            category_name = self.active_filter.split(":", 1)[1]
            if self.active_filter.startswith("tag:"):
                header_text = fmt(
                    "embeds.catalog.header_format_tag",
                    next_icon=next_icon,
                    category=category_name,
                )
            else:
                header_text = fmt(
                    "embeds.catalog.header_format_support",
                    next_icon=next_icon,
                    category=category_name,
                )
        else:
            header_text = fmt("embeds.catalog.header_format_all", next_icon=next_icon)

        lines = [f"## {header_text}"]
        space_emoji = resolve_emoji_string("space")
        difficulty_rating = {
            "Easy": "5/5",
            "Medium": "4/5",
            "Hard": "3/5",
        }

        for game_id in page_games:
            meta = self.game_metadata[game_id]
            game_name = meta["name"]
            game_emoji = get_game_emoji(game_id)
            difficulty = meta.get("difficulty", "Medium")
            rating = difficulty_rating.get(difficulty, "4/5")
            if not rating.endswith("/5"):
                rating = f"{rating}/5"
            playtime = meta.get("time") or "15min"
            player_count_str = _format_player_count(meta)

            tags_list = sorted(meta.get("tags", ()))
            tags_str = ", ".join(tags_list) or "Board Game"

            supports: list[str] = []
            if meta.get("supports_bots"):
                supports.append("Bots")
            if _meta_supports_roles(meta):
                supports.append("Roles")
            if meta.get("supports_replays"):
                supports.append("Replays")
            if meta.get("supports_lobby_options"):
                supports.append("Lobby Options")
            supports_str = ", ".join(supports) or "None"

            lines.extend(
                [
                    f"{game_emoji} **{game_name}**",
                    f"{space_emoji} **{rating}** ★ {playtime} `{player_count_str}`",
                    f"{space_emoji} *{tags_str}*",
                    f"{space_emoji} *Supports: {supports_str}*",
                ]
            )

        self.body_text = "\n".join(lines)

        container = StrifeContainer()
        append_blocks(
            container,
            summary_text_block(self.body_text),
            has_content=False,
        )
        container.add_item(discord.ui.Separator())

        brand_name = NAME or "PlayCord"
        if self.active_filter:
            category_name = self.active_filter.split(":", 1)[1]
            placeholder = fmt(
                "embeds.catalog.select_placeholder_filter",
                category=category_name,
                count=total_games,
            )
        else:
            placeholder = fmt(
                "embeds.catalog.select_placeholder_all",
                name=brand_name,
                count=total_games,
            )

        all_tags: set[str] = set()
        for meta in self.game_metadata.values():
            for tag in meta.get("tags", ()):
                all_tags.add(tag)
        sorted_tags = sorted(all_tags)

        support_features: set[str] = set()
        for meta in self.game_metadata.values():
            if meta.get("supports_bots"):
                support_features.add("Bots")
            if _meta_supports_roles(meta):
                support_features.add("Roles")
            if meta.get("supports_replays"):
                support_features.add("Replays")
            if meta.get("supports_lobby_options"):
                support_features.add("Lobby Options")
        sorted_supports = sorted(support_features)

        select_options: list[StrifeSelectOption | StrifeSelectCategory] = [
            StrifeSelectOption(
                label="All Games",
                value="all",
                emoji="playcord",
                default=(self.active_filter is None),
                description="Show all games",
            ),
            StrifeSelectCategory(title="By Type"),
        ]
        select_options.extend(
            StrifeSelectOption(
                label=tag,
                value=f"tag:{tag}",
                emoji="settings",
                default=(self.active_filter == f"tag:{tag}"),
            )
            for tag in sorted_tags
        )
        select_options.append(StrifeSelectCategory(title="By Support"))
        select_options.extend(
            StrifeSelectOption(
                label=sup,
                value=f"support:{sup}",
                emoji="settings",
                default=(self.active_filter == f"support:{sup}"),
            )
            for sup in sorted_supports
        )

        dropdown = StrifeDropdown(
            description="",
            placeholder=placeholder[:150],
            options=select_options,
            callback=self._on_select_change,
        )
        container.add_item(dropdown)

        if self.max_pages > 1:
            container.add_item(discord.ui.Separator())
            container.add_item(
                build_pagination_row(
                    current_page=self.current_page,
                    max_pages=self.max_pages,
                    first_callback=self._first_callback,
                    prev_callback=self._prev_callback,
                    page_callback=self._page_button_callback,
                    next_callback=self._next_callback,
                    last_callback=self._last_callback,
                ),
            )

        self.add_item(container)

    async def _first_callback(self, interaction: discord.Interaction) -> None:
        await self._navigate_page(interaction, 1)

    async def _prev_callback(self, interaction: discord.Interaction) -> None:
        await self._navigate_page(interaction, max(1, self.current_page - 1))

    async def _page_button_callback(self, interaction: discord.Interaction) -> None:
        if not self._validate_interaction(interaction):
            await _response_send_message(
                interaction,
                get("interactions.pagination_not_yours"),
                ephemeral=True,
                delete_after=EPHEMERAL_DELETE_AFTER,
            )
            return
        modal = StrifePageScrubModal(
            current_page=self.current_page,
            max_pages=self.max_pages,
            callback_handler=self._modal_navigate_page,
            title=get("pagination.modal_title", "Go to Page"),
            label=fmt(
                "pagination.modal_label",
                "Enter page (1-{max})",
                max=self.max_pages,
            ),
        )
        await interaction.response.send_modal(modal)

    async def _next_callback(self, interaction: discord.Interaction) -> None:
        await self._navigate_page(
            interaction,
            min(self.max_pages, self.current_page + 1),
        )

    async def _last_callback(self, interaction: discord.Interaction) -> None:
        await self._navigate_page(interaction, self.max_pages)

    async def _navigate_page(self, interaction: discord.Interaction, page: int) -> None:
        if not self._validate_interaction(interaction):
            await _response_send_message(
                interaction,
                get("interactions.pagination_not_yours"),
                ephemeral=True,
                delete_after=EPHEMERAL_DELETE_AFTER,
            )
            return
        self.current_page = page
        await interaction.response.defer()
        self.rebuild_layout()
        await interaction.edit_original_response(view=self)

    async def _modal_navigate_page(
        self,
        interaction: discord.Interaction,
        page: int,
    ) -> None:
        self.current_page = page
        self.rebuild_layout()
        await interaction.edit_original_response(view=self)

    async def _on_select_change(
        self,
        interaction: discord.Interaction,
        selected_value: str,
    ) -> None:
        if not self._validate_interaction(interaction):
            await _response_send_message(
                interaction,
                get("interactions.pagination_not_yours"),
                ephemeral=True,
                delete_after=EPHEMERAL_DELETE_AFTER,
            )
            return

        if selected_value == "all":
            self.active_filter = None
            self.current_page = 1
        else:
            self.active_filter = selected_value
            self.current_page = 1

        await interaction.response.defer()
        self.rebuild_layout()
        await interaction.edit_original_response(view=self)
