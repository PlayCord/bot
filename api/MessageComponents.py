from __future__ import annotations

import io
import typing
from dataclasses import dataclass
from itertools import count
from typing import Any, Callable, Iterable, Sequence

import discord
from discord import SelectOption

from api.Player import Player
from utils.emojis import parse_discord_emoji
from utils.table_renderer import render_table_as_png

ButtonStyle = discord.ButtonStyle
SeparatorSpacing = discord.SeparatorSpacing


class _BuildContext:
    def __init__(self, game_id: int | None) -> None:
        self.game_id = game_id
        self.attachments: list[discord.File] = []
        self._attachment_names: set[str] = set()
        self._counter = count(1)

    def _unique_filename(self, prefix: str, extension: str) -> str:
        while True:
            name = f"{prefix}_{next(self._counter)}.{extension}"
            if name not in self._attachment_names:
                self._attachment_names.add(name)
                return name

    def prepare_attachment(
        self,
        media: str | bytes | discord.File,
        *,
        prefix: str = "attachment",
        extension: str = "png",
    ) -> str:
        if isinstance(media, str):
            return media

        if isinstance(media, bytes):
            filename = self._unique_filename(prefix, extension)
            file = discord.File(io.BytesIO(media), filename=filename)
        elif isinstance(media, discord.File):
            filename = getattr(media, "filename", None) or self._unique_filename(prefix, extension)
            media.filename = filename
            self._attachment_names.add(filename)
            file = media
        else:
            raise TypeError(f"Unsupported attachment type: {type(media)!r}")

        self.attachments.append(file)
        return f"attachment://{file.filename}"


class LayoutNode:
    def build(self, ctx: _BuildContext) -> discord.ui.Item:
        raise NotImplementedError


class _GroupedNode(LayoutNode):
    pass


def _callback_name(callback: str | Callable[..., Any]) -> str:
    if callable(callback):
        return callback.__name__
    return str(callback)


def _coerce_text_node(node: str | "TextDisplay") -> str | discord.ui.TextDisplay:
    if isinstance(node, TextDisplay):
        return node.build(_BuildContext(game_id=None))
    return str(node)


def _normalize_row_children(children: Sequence[Any]) -> list[Any]:
    normalized: list[Any] = []
    pending_rows: dict[int, list[Button | Select]] = {}

    def flush_rows() -> None:
        if not pending_rows:
            return
        for row_index in sorted(pending_rows):
            normalized.append(ActionRow(*pending_rows[row_index]))
        pending_rows.clear()

    for child in children:
        if child is None:
            continue
        if isinstance(child, (Button, Select)):
            row_index = child.row if child.row is not None else 0
            pending_rows.setdefault(row_index, []).append(child)
        else:
            flush_rows()
            normalized.append(child)

    flush_rows()
    return normalized


def code_block(content: str, language: str = "") -> str:
    return f"```{language}\n{content}\n```"


def _display_name_for_table_row(value: Any) -> str:
    display_name = getattr(value, "display_name", None)
    if display_name:
        return str(display_name)

    name = getattr(value, "name", None)
    if name:
        return str(name)

    mention = getattr(value, "mention", None)
    if mention:
        return str(mention)

    return str(value)


def _table_headers_and_rows(data: dict[Any, dict[str, Any]]) -> tuple[list[str], list[list[str]]]:
    column_names: list[str] = []
    for values in data.values():
        for key in values:
            key_text = str(key)
            if key_text not in column_names:
                column_names.append(key_text)

    rows: list[list[str]] = []
    for player, values in data.items():
        row = [_display_name_for_table_row(player)]
        for column in column_names:
            row.append(str(values.get(column, "")))
        rows.append(row)

    return ["Name", *column_names], rows


def format_data_table(data: dict[Any, dict[str, Any]]) -> str:
    if not data:
        return "_No data_"

    headers, rows = _table_headers_and_rows(data)
    widths = [len(header) for header in headers]
    for row in rows:
        for index, value in enumerate(row):
            widths[index] = max(widths[index], len(value))

    def fmt_row(values: Sequence[str]) -> str:
        return " | ".join(value.ljust(widths[index]) for index, value in enumerate(values))

    sep = "-+-".join("-" * width for width in widths)
    lines = [fmt_row(headers), sep, *(fmt_row(row) for row in rows)]
    return code_block("\n".join(lines))


def format_data_table_image(data: dict[Any, dict[str, Any]]) -> bytes:
    if not data:
        return render_table_as_png(["Info"], [["No data"]])

    headers, rows = _table_headers_and_rows(data)
    return render_table_as_png(headers, rows)


@dataclass(slots=True)
class TextDisplay(_GroupedNode):
    content: str

    def build(self, ctx: _BuildContext) -> discord.ui.TextDisplay:
        return discord.ui.TextDisplay(self.content)


@dataclass(slots=True)
class Separator(_GroupedNode):
    visible: bool = True
    spacing: discord.SeparatorSpacing = discord.SeparatorSpacing.small

    def build(self, ctx: _BuildContext) -> discord.ui.Separator:
        return discord.ui.Separator(visible=self.visible, spacing=self.spacing)


@dataclass(slots=True)
class Thumbnail:
    media: str | bytes | discord.File
    description: str | None = None
    spoiler: bool = False

    def build(self, ctx: _BuildContext) -> discord.ui.Thumbnail:
        media = self.media
        if not isinstance(media, str):
            media = ctx.prepare_attachment(media, prefix="thumb")
        return discord.ui.Thumbnail(media, description=self.description, spoiler=self.spoiler)


@dataclass(slots=True)
class MediaGallery(_GroupedNode):
    items: tuple[str | bytes | discord.File | discord.MediaGalleryItem, ...]

    def __init__(self, *items: str | bytes | discord.File | discord.MediaGalleryItem) -> None:
        self.items = tuple(items)

    def build(self, ctx: _BuildContext) -> discord.ui.MediaGallery:
        built_items: list[discord.MediaGalleryItem] = []
        for item in self.items:
            if isinstance(item, discord.MediaGalleryItem):
                built_items.append(item)
                continue
            media = item
            if not isinstance(media, str):
                media = ctx.prepare_attachment(media, prefix="gallery")
            built_items.append(discord.MediaGalleryItem(media))
        return discord.ui.MediaGallery(*built_items)


@dataclass(slots=True)
class Button:
    label: str | None
    callback: Callable[[Player, dict], Any] | Callable[[Player], Any] | str
    emoji: str | None = None
    row: int | None = None
    style: discord.ButtonStyle = discord.ButtonStyle.secondary
    arguments: dict[str, Any] | None = None
    require_current_turn: bool = True
    disabled: bool = False

    def build(self, ctx: _BuildContext) -> discord.ui.Button:
        if ctx.game_id is None:
            raise ValueError("Interactive buttons require a game_id")
        args = ""
        if self.arguments:
            args = ",".join(f"{key}={value}" for key, value in self.arguments.items())
        prefix = "c" if self.require_current_turn else "n"
        return discord.ui.Button(
            style=self.style,
            label=self.label or "\u200b",
            emoji=parse_discord_emoji(self.emoji),
            custom_id=f"{prefix}/{ctx.game_id}/{_callback_name(self.callback)}/{args}",
            disabled=self.disabled,
        )


@dataclass(slots=True)
class Select:
    data: list[dict[str, Any]]
    callback: Callable[[Player, dict], Any] | Callable[[Player], Any] | str
    row: int | None = None
    require_current_turn: bool = True
    min_values: int | None = None
    max_values: int | None = None
    placeholder: str | None = None
    disabled: bool = False

    def build(self, ctx: _BuildContext) -> discord.ui.Select:
        if ctx.game_id is None:
            raise ValueError("Interactive selects require a game_id")
        options: list[SelectOption] = []
        for item in self.data:
            options.append(
                SelectOption(
                    label=str(item["label"])[:100],
                    value=str(item["value"])[:100],
                    emoji=parse_discord_emoji(item.get("emoji")),
                    default=bool(item.get("default", False)),
                    description=(str(item["description"])[:100] if item.get("description") is not None else None),
                )
            )
        prefix = "select_c" if self.require_current_turn else "select_n"
        return discord.ui.Select(
            options=options,
            min_values=self.min_values,
            max_values=self.max_values,
            placeholder=self.placeholder,
            disabled=self.disabled,
            custom_id=f"{prefix}/{ctx.game_id}/{_callback_name(self.callback)}",
        )


@dataclass(slots=True)
class ActionRow(_GroupedNode):
    children: tuple[Button | Select, ...]

    def __init__(self, *children: Button | Select) -> None:
        self.children = tuple(children)

    def build(self, ctx: _BuildContext) -> discord.ui.ActionRow:
        row = discord.ui.ActionRow()
        for child in self.children:
            row.add_item(child.build(ctx))
        return row


@dataclass(slots=True)
class Section(_GroupedNode):
    children: tuple[str | TextDisplay, ...]
    accessory: Button | Thumbnail

    def __init__(self, *children: str | TextDisplay, accessory: Button | Thumbnail) -> None:
        self.children = tuple(children)
        self.accessory = accessory

    def build(self, ctx: _BuildContext) -> discord.ui.Section:
        built_children = [_coerce_text_node(child) for child in self.children]
        return discord.ui.Section(*built_children, accessory=self.accessory.build(ctx))


@dataclass(slots=True)
class Container(_GroupedNode):
    children: tuple[Any, ...]
    accent_color: discord.Colour | int | None = None
    spoiler: bool = False

    def __init__(
        self,
        *children: Any,
        accent_color: discord.Colour | int | None = None,
        spoiler: bool = False,
    ) -> None:
        self.children = tuple(children)
        self.accent_color = accent_color
        self.spoiler = spoiler

    def build(self, ctx: _BuildContext) -> discord.ui.Container:
        built = [build_child(child, ctx) for child in _normalize_row_children(self.children)]
        return discord.ui.Container(*built, accent_color=self.accent_color, spoiler=self.spoiler)


def build_child(child: Any, ctx: _BuildContext) -> discord.ui.Item:
    if isinstance(child, LayoutNode):
        return child.build(ctx)
    if isinstance(child, str):
        return TextDisplay(child).build(ctx)
    raise TypeError(f"Unsupported message child: {type(child)!r}")


@dataclass(slots=True)
class Message:
    children: tuple[Any, ...]
    files: list[discord.File] | None = None

    def __init__(self, *children: Any, files: list[discord.File] | None = None) -> None:
        self.children = tuple(children)
        self.files = files

    def _build(self, game_id: int | None = None) -> tuple[discord.ui.LayoutView, list[discord.File]]:
        ctx = _BuildContext(game_id)
        if self.files:
            for file in self.files:
                ctx.prepare_attachment(file, prefix="message")
        view = discord.ui.LayoutView(timeout=None)
        for child in _normalize_row_children(self.children):
            view.add_item(build_child(child, ctx))
        return view, ctx.attachments

    def to_layout_view(self, game_id: int | None = None) -> discord.ui.LayoutView:
        view, _ = self._build(game_id)
        return view

    def to_send_kwargs(self, game_id: int | None = None, *, content: str | None = None) -> dict[str, Any]:
        view, files = self._build(game_id)
        kwargs: dict[str, Any] = {"view": view}
        if content is not None:
            kwargs["content"] = content
        if files:
            kwargs["files"] = files
        return kwargs

    def to_edit_kwargs(self, game_id: int | None = None, *, content: str | None = None) -> dict[str, Any]:
        view, files = self._build(game_id)
        kwargs: dict[str, Any] = {"view": view, "attachments": files}
        if content is not None:
            kwargs["content"] = content
        return kwargs


@dataclass(slots=True)
class ThreadMessage:
    key: str
    content: Message
