"""Matchmaking lobby LayoutView (Join/Leave/Ready + optional selects)."""

from __future__ import annotations

import discord
from discord import SelectOption

from playcord.infrastructure.constants import (
    BUTTON_PREFIX_LOBBY_OPT,
    BUTTON_PREFIX_LOBBY_ROLE,
    BUTTON_PREFIX_LOBBY_SETTINGS_END,
    BUTTON_PREFIX_LOBBY_SETTINGS_PRIV,
    BUTTON_PREFIX_LOBBY_SETTINGS_RESET_PRIV,
    BUTTON_PREFIX_LOBBY_SETTINGS_RESET_RULES,
)
from playcord.infrastructure.locale import get
from playcord.presentation.ui.component_kit import (
    format_page_title,
    icon_for_select_option,
    primary_button,
    secondary_button,
    small_text,
)
from playcord.presentation.ui.emojis import get_emoji_string, icon_for_button
from playcord.presentation.ui.containers import (
    TEXT_DISPLAY_MAX,
    _add_text_sections,
)


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
        has_text = False
        if text_sections:
            _add_text_sections(container, text_sections)
            has_text = bool(text_sections)
        elif summary_text:
            container.add_item(discord.ui.TextDisplay(summary_text[:TEXT_DISPLAY_MAX]))
            has_text = True
        if table_image_url:
            if has_text:
                container.add_item(discord.ui.Separator())
            container.add_item(
                discord.ui.MediaGallery(
                    discord.MediaGalleryItem(table_image_url),
                ),
            )
        if has_text or table_image_url:
            container.add_item(discord.ui.Separator())

        action_row = discord.ui.ActionRow()
        join_btn_factory = (
            secondary_button if ready_button_id is not None else primary_button
        )
        join_btn = join_btn_factory(
            label=get("buttons.join"),
            custom_id=join_button_id,
            icon="join",
        )
        join_btn.callback = self._route_to_cog
        action_row.add_item(join_btn)

        leave_btn = secondary_button(
            label=get("buttons.leave"),
            custom_id=leave_button_id,
            icon="leave",
        )
        leave_btn.callback = self._route_to_cog
        action_row.add_item(leave_btn)

        if ready_button_id is not None:
            ready_btn = primary_button(
                label=ready_button_label,
                custom_id=ready_button_id,
                icon="ready",
            )
            ready_btn.callback = self._route_to_cog
            action_row.add_item(ready_btn)

        if assign_roles_button_id is not None:
            assign_btn = secondary_button(
                label=get("buttons.assign_roles"),
                custom_id=assign_roles_button_id,
                icon="assign_roles",
            )
            assign_btn.callback = self._route_to_cog
            action_row.add_item(assign_btn)

        if settings_button_id is not None:
            settings_btn = secondary_button(
                label=get("buttons.settings"),
                custom_id=settings_button_id,
                icon="settings",
            )
            settings_btn.callback = self._route_to_cog
            action_row.add_item(settings_btn)

        container.add_item(action_row)

        if role_specs:
            container.add_item(discord.ui.Separator())
            container.add_item(
                discord.ui.TextDisplay(get("queue.section_role_selection"))
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
            role_row = discord.ui.ActionRow()
            role_row.add_item(rsel)
            container.add_item(role_row)

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

        container = discord.ui.Container()
        _add_text_sections(
            container,
            [
                format_page_title(
                    f"{game_name} {get_emoji_string('forward')} {get('settings.ephemeral_title_suffix')}",
                    icon_key="settings",
                ),
                get("settings.section_privacy"),
                (
                    get("settings.privacy_current_private")
                    if private
                    else get("settings.privacy_current_public")
                ),
            ],
        )
        container.add_item(
            discord.ui.TextDisplay(small_text(get("settings.privacy_select_description"))),
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
        privacy_row = discord.ui.ActionRow()
        privacy_row.add_item(privacy_sel)
        container.add_item(privacy_row)

        reset_privacy_btn = secondary_button(
            label=get("buttons.reset_privacy"),
            custom_id=f"{BUTTON_PREFIX_LOBBY_SETTINGS_RESET_PRIV}{lobby_key}",
            icon="back",
        )
        reset_privacy_btn.callback = self._route_to_cog
        reset_privacy_row = discord.ui.ActionRow()
        reset_privacy_row.add_item(reset_privacy_btn)
        container.add_item(reset_privacy_row)

        if access_list_label:
            container.add_item(discord.ui.Separator())
            _add_text_sections(
                container,
                [
                    get("settings.section_access"),
                    (
                        f"{access_list_label}\n"
                        f"{access_list_value or get('settings.lists_empty')}"
                    ),
                ],
            )

        if option_specs:
            container.add_item(discord.ui.Separator())
            container.add_item(
                discord.ui.TextDisplay(get("settings.section_match_options")),
            )

        for spec in option_specs:
            if spec.description:
                container.add_item(discord.ui.TextDisplay(small_text(spec.description)))
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
            option_row = discord.ui.ActionRow()
            option_row.add_item(sel)
            container.add_item(option_row)

        if option_specs:
            reset_rules_btn = secondary_button(
                label=get("buttons.reset_game_rules"),
                custom_id=f"{BUTTON_PREFIX_LOBBY_SETTINGS_RESET_RULES}{lobby_key}",
                icon="back",
            )
            reset_rules_btn.callback = self._route_to_cog
            reset_rules_row = discord.ui.ActionRow()
            reset_rules_row.add_item(reset_rules_btn)
            container.add_item(reset_rules_row)

        container.add_item(discord.ui.Separator())
        end_row = discord.ui.ActionRow()
        end_btn = discord.ui.Button(
            label=get("buttons.end_game"),
            style=discord.ButtonStyle.danger,
            custom_id=f"{BUTTON_PREFIX_LOBBY_SETTINGS_END}{lobby_key}",
            emoji=icon_for_button("leave"),
        )
        end_btn.callback = self._route_to_cog
        end_row.add_item(end_btn)
        container.add_item(end_row)

        self.add_item(container)
