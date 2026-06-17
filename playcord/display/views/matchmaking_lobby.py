"""Matchmaking lobby LayoutView (Join/Leave/Ready + optional selects)."""

from __future__ import annotations

import discord
from discord import SelectOption
from playcord.presentation.ui.component_kit import (
    format_page_title,
    icon_for_select_option,
    primary_button,
    secondary_button,
)
from playcord.presentation.ui.emojis import get_icon, icon_for_button
from playcord.presentation.ui.presets import (
    append_blocks,
    button_row,
    divider,
    labeled_select,
    media_block,
    summary_text_block,
    text_block,
    text_sections_block,
)

from playcord.infrastructure.constants import (
    BUTTON_PREFIX_LOBBY_OPT,
    BUTTON_PREFIX_LOBBY_ROLE,
    BUTTON_PREFIX_LOBBY_SETTINGS_END,
    BUTTON_PREFIX_LOBBY_SETTINGS_PRIV,
    BUTTON_PREFIX_LOBBY_SETTINGS_RESET_PRIV,
    BUTTON_PREFIX_LOBBY_SETTINGS_RESET_RULES,
)
from playcord.infrastructure.locale import get


class MatchmakingLobbyView(discord.ui.LayoutView):
    """
    Join / leave / optional Ready, optional per-player role selects for games with
    CHOSEN role mode. Match options live in the ephemeral settings panel.
    """

    async def _route_to_cog(self, interaction: discord.Interaction) -> None:
        """Persistent components are handled in MatchmakingCog.on_interaction."""

    def __init__(
            self,
            join_button_id: str,
            leave_button_id: str,
            ready_button_id: str | None,
            ready_button_label: str,
            lobby_key: int,
            role_specs: list[tuple[int, str, tuple[str, ...]]] | None = None,
            current_role_values: dict[int, str] | None = None,
            assign_roles_button_id: str | None = None,
            settings_button_id: str | None = None,
            summary_text: str | None = None,
            text_sections: list[str] | None = None,
            table_image_url: str | None = None,
    ) -> None:
        super().__init__(timeout=None)
        current_role_values = dict(current_role_values) if current_role_values else {}
        role_specs = role_specs or []

        container = discord.ui.Container()
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

        join_btn_factory = (
            secondary_button if ready_button_id is not None else primary_button
        )
        join_btn = join_btn_factory(
            label=get("buttons.join"),
            custom_id=join_button_id,
            icon="join",
        )
        join_btn.callback = self._route_to_cog

        leave_btn = secondary_button(
            label=get("buttons.leave"),
            custom_id=leave_button_id,
            icon="leave",
        )
        leave_btn.callback = self._route_to_cog

        action_buttons: list[discord.ui.Button] = [join_btn, leave_btn]

        if ready_button_id is not None:
            ready_btn = primary_button(
                label=ready_button_label,
                custom_id=ready_button_id,
                icon="ready",
            )
            ready_btn.callback = self._route_to_cog
            action_buttons.append(ready_btn)

        if assign_roles_button_id is not None:
            assign_btn = secondary_button(
                label=get("buttons.assign_roles"),
                custom_id=assign_roles_button_id,
                icon="assign_roles",
            )
            assign_btn.callback = self._route_to_cog
            action_buttons.append(assign_btn)

        if settings_button_id is not None:
            settings_btn = secondary_button(
                label=get("buttons.settings"),
                custom_id=settings_button_id,
                icon="settings",
            )
            settings_btn.callback = self._route_to_cog
            action_buttons.append(settings_btn)

        append_blocks(container, button_row(*action_buttons), has_content=False)

        if role_specs:
            append_blocks(
                container,
                divider(),
                text_block(get("queue.section_role_selection")),
                has_content=True,
            )
        for player_id, display_name, avail_roles in role_specs:
            cur = current_role_values.get(player_id)
            roptions: list[SelectOption] = []
            for r in avail_roles:
                rv = str(r)[:100]
                role_kwargs: dict = {
                    "label": str(r).replace("_", " ").title()[:100],
                    "value": rv,
                    "default": (cur is not None and str(cur) == str(r)),
                }
                role_emoji = icon_for_select_option("assign_roles")
                if role_emoji is not None:
                    role_kwargs["emoji"] = role_emoji
                roptions.append(SelectOption(**role_kwargs))
            placeholder = f"{display_name[:80]}: role"
            rsel = discord.ui.Select(
                custom_id=f"{BUTTON_PREFIX_LOBBY_ROLE}{lobby_key}/{player_id}",
                placeholder=placeholder[:150],
                min_values=1,
                max_values=1,
                options=roptions,
            )
            rsel.callback = self._route_to_cog
            append_blocks(
                container,
                labeled_select("", rsel, use_small_text=False),
                has_content=True,
            )

        self.add_item(container)


class LobbySettingsView(discord.ui.LayoutView):
    """Ephemeral lobby configuration: privacy, access lists, and match options."""

    async def _route_to_cog(self, interaction: discord.Interaction) -> None:
        """Persistent components are handled in MatchmakingCog.on_interaction."""

    def __init__(
            self,
            *,
            lobby_key: int,
            game_name: str,
            private: bool,
            access_list_label: str | None,
            access_list_value: str | None,
            option_specs: tuple = (),
            current_values: dict[str, str | int] | None = None,
    ) -> None:
        super().__init__(timeout=None)
        current_values = dict(current_values) if current_values else {}

        next_icon = get_icon("forward")
        title_suffix = get("settings.ephemeral_title_suffix")
        title_text = (
            f"{game_name} {next_icon} {title_suffix}"
            if next_icon
            else f"{game_name} {title_suffix}"
        )

        container = discord.ui.Container()
        has_content = append_blocks(
            container,
            text_sections_block(
                [
                    format_page_title(title_text, icon_key="settings"),
                    get("settings.section_privacy"),
                    (
                        get("settings.privacy_current_private")
                        if private
                        else get("settings.privacy_current_public")
                    ),
                ],
            ),
            has_content=False,
        )

        privacy_options: list[SelectOption] = []
        for label, value, is_public in (
                (get("queue.public_status"), "public", True),
                (get("queue.private_status"), "private", False),
        ):
            option_kwargs: dict = {
                "label": label[:100],
                "value": value,
                "default": (private is not is_public),
            }
            emoji = icon_for_select_option("settings")
            if emoji is not None:
                option_kwargs["emoji"] = emoji
            privacy_options.append(SelectOption(**option_kwargs))
        privacy_sel = discord.ui.Select(
            custom_id=f"{BUTTON_PREFIX_LOBBY_SETTINGS_PRIV}{lobby_key}",
            placeholder=get("settings.section_privacy")[:150],
            min_values=1,
            max_values=1,
            options=privacy_options,
        )
        privacy_sel.callback = self._route_to_cog
        has_content = append_blocks(
            container,
            labeled_select(get("settings.privacy_select_description"), privacy_sel),
            has_content=has_content,
        )

        reset_privacy_btn = secondary_button(
            label=get("buttons.reset_privacy"),
            custom_id=f"{BUTTON_PREFIX_LOBBY_SETTINGS_RESET_PRIV}{lobby_key}",
            icon="previous",
        )
        reset_privacy_btn.callback = self._route_to_cog
        has_content = append_blocks(
            container,
            button_row(reset_privacy_btn),
            has_content=has_content,
        )

        if access_list_label:
            has_content = append_blocks(
                container,
                divider(),
                text_sections_block(
                    [
                        get("settings.section_access"),
                        (
                            f"{access_list_label}\n"
                            f"{access_list_value or get('settings.lists_empty')}"
                        ),
                    ],
                ),
                has_content=has_content,
            )

        if option_specs:
            has_content = append_blocks(
                container,
                divider(),
                text_block(get("settings.section_match_options")),
                has_content=has_content,
            )

        for spec in option_specs:
            cur = current_values.get(spec.key, spec.default)
            options: list[SelectOption] = []
            for label, value, _is_def, icon_key in spec.select_options():
                option_kwargs = {
                    "label": label[:100],
                    "value": value[:100],
                    "default": (str(value) == str(cur)),
                }
                option_emoji = icon_for_select_option(icon_key or "settings")
                if option_emoji is not None:
                    option_kwargs["emoji"] = option_emoji
                options.append(SelectOption(**option_kwargs))
            sel = discord.ui.Select(
                custom_id=f"{BUTTON_PREFIX_LOBBY_OPT}{lobby_key}/{spec.key}",
                placeholder=spec.label[:150],
                min_values=1,
                max_values=1,
                options=options,
            )
            sel.callback = self._route_to_cog
            description = spec.description or ""
            has_content = append_blocks(
                container,
                labeled_select(description, sel),
                has_content=has_content,
            )

        if option_specs:
            reset_rules_btn = secondary_button(
                label=get("buttons.reset_game_rules"),
                custom_id=f"{BUTTON_PREFIX_LOBBY_SETTINGS_RESET_RULES}{lobby_key}",
                icon="previous",
            )
            reset_rules_btn.callback = self._route_to_cog
            has_content = append_blocks(
                container,
                button_row(reset_rules_btn),
                has_content=has_content,
            )

        end_btn = discord.ui.Button(
            label=get("buttons.end_game"),
            style=discord.ButtonStyle.danger,
            custom_id=f"{BUTTON_PREFIX_LOBBY_SETTINGS_END}{lobby_key}",
            emoji=icon_for_button("leave"),
        )
        end_btn.callback = self._route_to_cog
        append_blocks(
            container,
            divider(),
            button_row(end_btn),
            has_content=has_content,
        )

        self.add_item(container)
