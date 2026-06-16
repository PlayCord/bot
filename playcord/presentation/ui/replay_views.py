"""Interactive replay viewer layout."""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import urlencode

import discord
from discord import SelectOption

from playcord.infrastructure.constants import (
    BUTTON_PREFIX_REPLAY_NAV,
    BUTTON_PREFIX_REPLAY_NOOP,
)
from playcord.infrastructure.locale import fmt, get
from playcord.presentation.ui.component_kit import (
    icon_for_select_option,
    primary_button,
    secondary_button,
)
from playcord.presentation.ui.presets import (
    append_blocks,
    button_row,
    divider,
    labeled_select,
    text_block,
    title_block,
)

if TYPE_CHECKING:
    from playcord.api import MessageLayout


class ReplayViewerView(discord.ui.LayoutView):
    def __init__(
        self,
        *,
        match_id: int,
        owner_id: int,
        frame_index: int,
        total_frames: int,
        title: str,
        global_summary: str | None,
        frame_layout: MessageLayout,
    ) -> None:
        super().__init__(timeout=None)
        total = max(1, total_frames)
        frame = max(0, min(frame_index, total - 1))

        container = discord.ui.Container()
        append_blocks(container, title_block(title, icon_key="replay"), has_content=False)
        if global_summary:
            append_blocks(
                container,
                text_block(global_summary),
                divider(),
                has_content=True,
            )

        append_blocks(container, text_block(frame_layout.content or ""), has_content=True)
        if frame_layout.content and (frame_layout.buttons or frame_layout.selects):
            container.add_item(discord.ui.Separator())
        self._append_layout_components(container, match_id, frame, frame_layout)

        if frame_layout.buttons or frame_layout.selects:
            container.add_item(discord.ui.Separator())

        move_label = fmt(
            "commands.replay.move_indicator",
            current=frame,
            max=max(total - 1, 0),
        )
        nav_buttons: list[discord.ui.Button] = []
        nav_specs = [
            ("first", get("commands.replay.nav_first"), 0, frame == 0),
            ("previous", get("commands.replay.nav_prev"), max(0, frame - 1), frame == 0),
            ("info", move_label, frame, True),
            (
                "next",
                get("commands.replay.nav_next"),
                min(total - 1, frame + 1),
                frame >= total - 1,
            ),
            ("last", get("commands.replay.nav_last"), total - 1, frame >= total - 1),
        ]
        for btn_index, (icon_key, label, target, disabled) in enumerate(nav_specs):
            custom_id = self._nav_custom_id(
                match_id=match_id,
                owner_id=owner_id,
                target_frame=target,
                button_index=btn_index,
            )
            if icon_key == "info" or disabled:
                button = secondary_button(
                    label=label,
                    custom_id=custom_id,
                    icon=icon_key if icon_key != "info" else "replay",
                    disabled=disabled,
                )
            else:
                button = primary_button(
                    label=label,
                    custom_id=custom_id,
                    icon=icon_key,
                )
            button.callback = self._route_to_cog
            nav_buttons.append(button)
        append_blocks(container, button_row(*nav_buttons), has_content=True)

        if total > 1:
            seek = discord.ui.Select(
                custom_id=self._seek_custom_id(match_id=match_id, owner_id=owner_id),
                placeholder=get("commands.replay.seek_placeholder"),
                min_values=1,
                max_values=1,
                options=self._seek_options(total=total, current=frame),
            )
            seek.callback = self._route_to_cog
            append_blocks(
                container,
                labeled_select("", seek, use_small_text=False),
                has_content=True,
            )
        self.add_item(container)

    @staticmethod
    async def _route_to_cog(interaction: discord.Interaction) -> None:
        # Routed through GamesCog.on_interaction via custom_id prefix.
        pass

    @staticmethod
    def _append_layout_components(
        container: discord.ui.Container,
        match_id: int,
        frame_index: int,
        layout: MessageLayout,
    ) -> None:
        style_map = {
            "primary": discord.ButtonStyle.primary,
            "secondary": discord.ButtonStyle.secondary,
            "success": discord.ButtonStyle.success,
            "danger": discord.ButtonStyle.danger,
        }
        width = layout.button_row_width
        component_id = 0
        if width and width > 0 and layout.buttons:
            row_buttons: list[discord.ui.Button] = []
            for spec in layout.buttons:
                row_buttons.append(
                    discord.ui.Button(
                        label=(
                            spec.label
                            if (spec.label is not None and spec.label.strip())
                            else "\u200b"
                        ),
                        emoji=spec.emoji,
                        style=style_map[spec.style],
                        custom_id=ReplayViewerView._noop_custom_id(
                            match_id=match_id,
                            frame_index=frame_index,
                            component_id=component_id,
                        ),
                        disabled=True,
                    ),
                )
                component_id += 1
                if len(row_buttons) >= width:
                    row = discord.ui.ActionRow()
                    for button in row_buttons:
                        row.add_item(button)
                    container.add_item(row)
                    row_buttons = []
            if row_buttons:
                row = discord.ui.ActionRow()
                for button in row_buttons:
                    row.add_item(button)
                container.add_item(row)
        else:
            for spec in layout.buttons:
                row = discord.ui.ActionRow()
                row.add_item(
                    discord.ui.Button(
                        label=(
                            spec.label
                            if (spec.label is not None and spec.label.strip())
                            else "\u200b"
                        ),
                        emoji=spec.emoji,
                        style=style_map[spec.style],
                        custom_id=ReplayViewerView._noop_custom_id(
                            match_id=match_id,
                            frame_index=frame_index,
                            component_id=component_id,
                        ),
                        disabled=True,
                    ),
                )
                component_id += 1
                container.add_item(row)

        for spec in layout.selects:
            options: list[SelectOption] = []
            for option in spec.options:
                label = option.label if option.label.strip() else option.value
                options.append(
                    SelectOption(
                        label=label[:100],
                        value=option.value[:100],
                        default=option.default,
                    ),
                )
            row = discord.ui.ActionRow()
            row.add_item(
                discord.ui.Select(
                    custom_id=ReplayViewerView._noop_custom_id(
                        match_id=match_id,
                        frame_index=frame_index,
                        component_id=component_id,
                    ),
                    placeholder=spec.placeholder,
                    options=options,
                    disabled=True,
                ),
            )
            component_id += 1
            container.add_item(row)

    @staticmethod
    def _bookmark_frames(total: int) -> list[int]:
        if total <= 25:
            return list(range(total))
        bookmarks = {0, total - 1}
        span = total - 1
        for i in range(1, 24):
            bookmarks.add(round((span * i) / 24))
        return sorted(bookmarks)

    def _seek_options(self, *, total: int, current: int) -> list[SelectOption]:
        options: list[SelectOption] = []
        for frame in self._bookmark_frames(total):
            option_kwargs: dict = {
                "label": fmt("commands.replay.seek_option", move=frame)[:100],
                "value": str(frame),
                "default": (frame == current),
            }
            seek_emoji = icon_for_select_option("replay")
            if seek_emoji is not None:
                option_kwargs["emoji"] = seek_emoji
            options.append(SelectOption(**option_kwargs))
        return options[:25]

    @staticmethod
    def _nav_custom_id(
        *,
        match_id: int,
        owner_id: int,
        target_frame: int,
        button_index: int = 0,
    ) -> str:
        payload = urlencode(
            {
                "match_id": str(match_id),
                "owner": str(owner_id),
                "frame": str(target_frame),
                "btn": str(button_index),
            },
        )
        return f"{BUTTON_PREFIX_REPLAY_NAV}{match_id}/{payload}"

    @staticmethod
    def _seek_custom_id(*, match_id: int, owner_id: int) -> str:
        payload = urlencode(
            {
                "match_id": str(match_id),
                "owner": str(owner_id),
                "mode": "seek",
            },
        )
        return f"{BUTTON_PREFIX_REPLAY_NAV}{match_id}/{payload}"

    @staticmethod
    def _noop_custom_id(*, match_id: int, frame_index: int, component_id: int) -> str:
        payload = urlencode({"frame": str(frame_index), "id": str(component_id)})
        return f"{BUTTON_PREFIX_REPLAY_NOOP}{match_id}/{payload}"
