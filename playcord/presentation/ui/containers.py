from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import discord

from playcord.infrastructure.constants import (
    ERROR_COLOR,
    SUCCESS_COLOR,
)
from playcord.infrastructure.locale import fmt, get
from playcord.presentation.interactions.contextify import contextify
from playcord.presentation.ui.component_kit import format_page_title, icon_prefix

_TEXT_DISPLAY_MAX = 4000
# Discord TextDisplay / message content limit
# (public alias for callers outside this module)
TEXT_DISPLAY_MAX = _TEXT_DISPLAY_MAX
_FIELD_VALUE_MAX = 1024
_FIELD_LINE_SAFE_MAX = 500
# Embed field value max minus small safety margin for markdown/formatting overhead
_FIELD_VALUE_SAFE = _FIELD_VALUE_MAX - 7

# Discord's maximum embed fields
MAX_EMBED_FIELDS = 25


def _chunk_text(text: str, *, max_len: int = _TEXT_DISPLAY_MAX) -> list[str]:
    if not text:
        return []
    chunks: list[str] = []
    current = ""
    for line in text.splitlines(keepends=True):
        if len(current) + len(line) > max_len and current:
            chunks.append(current.rstrip("\n"))
            current = line
        else:
            current += line
    if current:
        chunks.append(current.rstrip("\n"))
    return chunks or [text[:max_len]]


def chunk_text_display_lines(
    text: str,
    *,
    max_len: int = TEXT_DISPLAY_MAX,
) -> list[str]:
    """Split content into Discord TextDisplay-sized chunks (newline-aware)."""
    return _chunk_text(text, max_len=max_len)


def _add_text_sections(
    ui_container: discord.ui.Container,
    sections: list[str],
) -> None:
    for index, section in enumerate(sections):
        section = section.strip()
        if not section:
            continue
        if index > 0:
            ui_container.add_item(discord.ui.Separator(visible=False))
        for chunk in _chunk_text(section):
            ui_container.add_item(discord.ui.TextDisplay(chunk))


def _build_container_view(
    body_text: str,
    *,
    accent_color: discord.Color | int | None = None,
    media_urls: Iterable[str] | None = None,
    thumbnail_url: str | None = None,
    text_sections: list[str] | None = None,
) -> discord.ui.LayoutView:
    view = discord.ui.LayoutView(timeout=None)
    container = discord.ui.Container(accent_color=accent_color)
    body_text = (body_text or "").strip()
    if text_sections:
        _add_text_sections(container, text_sections)
    elif body_text:
        for chunk in _chunk_text(body_text):
            container.add_item(discord.ui.TextDisplay(chunk))
    urls = [u for u in (media_urls or []) if u]
    if thumbnail_url:
        urls.insert(0, thumbnail_url)
    has_text = bool(text_sections) or bool(body_text)
    if urls:
        if has_text:
            container.add_item(discord.ui.Separator())
        items = [discord.MediaGalleryItem(url) for url in urls]
        container.add_item(discord.ui.MediaGallery(*items))
    view.add_item(container)
    return view


def _build_container_view_from_card(card: "CustomContainer") -> discord.ui.LayoutView:
    return _build_container_view(
        "",
        accent_color=card.color,
        media_urls=card.media_urls(),
        thumbnail_url=card.thumbnail_url,
        text_sections=card.text_sections(),
    )


def container_to_markdown(card: "CustomContainer | str | None") -> str:
    if card is None:
        return ""
    if isinstance(card, str):
        return card.strip()
    to_markdown = getattr(card, "to_markdown", None)
    if callable(to_markdown):
        return str(to_markdown()).strip()
    return str(card).strip()


def container_send_kwargs(
    card: "CustomContainer | str",
    *,
    files: list[discord.File] | None = None,
    content: str | None = None,
) -> dict[str, Any]:
    if isinstance(card, CustomContainer):
        kwargs: dict[str, Any] = {"view": _build_container_view_from_card(card)}
    else:
        body = container_to_markdown(card)
        kwargs = {"view": _build_container_view(body)}
    if files:
        kwargs["files"] = files
    if content is not None:
        kwargs["content"] = content
    return kwargs


def container_edit_kwargs(
    card: "CustomContainer | str",
    *,
    attachments: list[discord.File] | None = None,
    content: str | None = None,
) -> dict[str, Any]:
    if isinstance(card, CustomContainer):
        kwargs: dict[str, Any] = {"view": _build_container_view_from_card(card)}
    else:
        body = container_to_markdown(card)
        kwargs = {
            "view": _build_container_view(body),
        }
    if attachments is not None:
        kwargs["attachments"] = attachments
    if content is not None:
        kwargs["content"] = content
    return kwargs


def lines_to_container_sections(
    lines: list[str],
    *,
    value_max: int = _FIELD_VALUE_MAX,
    line_max: int = _FIELD_LINE_SAFE_MAX,
) -> list[str]:
    safe: list[str] = []
    for ln in lines:
        if len(ln) <= line_max:
            safe.append(ln)
        else:
            safe.append(ln[: line_max - 1] + "…")

    chunks: list[str] = []
    bucket: list[str] = []
    size = 0
    for line in safe:
        add = len(line) + (1 if bucket else 0)
        if bucket and size + add > value_max:
            chunks.append("\n".join(bucket))
            bucket = [line]
            size = len(line)
        else:
            bucket.append(line)
            size += add
    if bucket:
        chunks.append("\n".join(bucket))
    return chunks


def append_container_sections(
    card: "CustomContainer",
    chunks: list[str],
    *,
    first_name: str,
    more_name: str = "\u200b",
    truncated_note: str | None = None,
    max_fields: int = 24,
) -> None:
    vm = _FIELD_VALUE_MAX
    for i, chunk in enumerate(chunks):
        if len(card.fields) >= max_fields:
            if truncated_note:
                card.add_field(name="\u200b", value=truncated_note, inline=False)
            return
        name = (first_name if i == 0 else more_name)[:256]
        val = chunk if len(chunk) <= vm else chunk[: vm - 1] + "…"
        card.add_field(name=name, value=val or "\u200b", inline=False)


@dataclass(slots=True)
class ContainerField:
    name: str
    value: str
    inline: bool = True


class CustomContainer:
    def __init__(self, **kwargs) -> None:
        self.title: str | None = kwargs.get("title")
        self.title_icon: str | None = kwargs.get("title_icon")
        self.description: str | None = kwargs.get("description")
        self.color: discord.Color | int | None = kwargs.get("color")
        self.fields: list[ContainerField] = []
        self.footer_text: str | None = None
        self.footer_icon_url: str | None = None
        self.image_url: str | None = None
        self.thumbnail_url: str | None = None

    @property
    def footer(self):
        if self.footer_text is None:
            return None
        return SimpleNamespace(text=self.footer_text, icon_url=self.footer_icon_url)

    def remove_footer(self):
        self.footer_text = None
        self.footer_icon_url = None
        return self

    def add_field(self, *, name: str, value: Any, inline: bool = True):
        if len(self.fields) >= MAX_EMBED_FIELDS:
            msg = (
                f"Cannot add field: container already has {MAX_EMBED_FIELDS} fields (Discord's limit). "
                f"Field name: {name[:50]}"
            )
            raise ValueError(msg)
        self.fields.append(ContainerField(str(name), str(value), inline))
        return self

    def set_footer(self, *, text: str | None = None, icon_url: str | None = None):
        self.footer_text = text
        self.footer_icon_url = icon_url
        return self

    def set_image(self, *, url: str):
        self.image_url = url
        return self

    def set_thumbnail(self, *, url: str):
        self.thumbnail_url = url
        return self

    def media_urls(self) -> list[str]:
        out: list[str] = []
        if self.image_url:
            out.append(self.image_url)
        return out

    def validate(self) -> None:
        """Validate container doesn't exceed Discord's limits."""
        if len(self.fields) > MAX_EMBED_FIELDS:
            msg = f"Container has {len(self.fields)} fields, exceeds limit of {MAX_EMBED_FIELDS}"
            raise ValueError(msg)

    def text_sections(self) -> list[str]:
        """Logical TextDisplay blocks for Components V2 layout."""
        sections: list[str] = []
        if self.title:
            sections.append(
                format_page_title(self.title, icon_key=self.title_icon),
            )
        if self.description:
            sections.append(str(self.description))
        sections.extend(f"{field.name}\n{field.value}" for field in self.fields)
        if self.footer_text:
            sections.append(str(self.footer_text))
        return sections

    def to_markdown(self) -> str:
        return "\n\n".join(
            section for section in self.text_sections() if section.strip()
        ).strip()

    def to_send_kwargs(
        self,
        *,
        files: list[discord.File] | None = None,
        content: str | None = None,
    ) -> dict[str, Any]:
        return container_send_kwargs(self, files=files, content=content)

    def to_edit_kwargs(
        self,
        *,
        attachments: list[discord.File] | None = None,
        content: str | None = None,
    ) -> dict[str, Any]:
        return container_edit_kwargs(self, attachments=attachments, content=content)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        if self.title is not None:
            result["title"] = self.title
        if self.description is not None:
            result["description"] = self.description
        if self.footer_text is not None:
            result["footer"] = {"text": self.footer_text}
        if self.fields:
            result["fields"] = [
                {"name": f.name, "value": f.value, "inline": f.inline}
                for f in self.fields
            ]
        return result


class SuccessContainer(CustomContainer):
    def __init__(
        self,
        title: str | None = None,
        description: str | None = None,
        **kwargs,
    ) -> None:
        kwargs["color"] = SUCCESS_COLOR
        resolved_title = title or get("success.default_title")
        kwargs["title"] = icon_prefix("success", resolved_title)
        if description:
            kwargs["description"] = description
        super().__init__(**kwargs)


class UserErrorContainer(CustomContainer):
    def __init__(
        self,
        description: str | None = None,
        suggestion: str | None = None,
        **kwargs,
    ) -> None:
        kwargs["color"] = ERROR_COLOR
        super().__init__(**kwargs)
        if description:
            self.description = icon_prefix("error", description)
        if suggestion:
            base = self.description or ""
            self.description = f"{base}\n\n{suggestion}" if base else str(suggestion)


class ErrorContainer(CustomContainer):
    def __init__(self, ctx=None, what_failed=None, reason=None) -> None:
        current_directory = str(Path(__file__).resolve().parent)
        super().__init__(
            title=icon_prefix("error", get("system_error.title")),
            color=ERROR_COLOR,
        )
        self.add_field(
            name=get("system_error.report_field"),
            value=fmt(
                "system_error.report_value",
                github_issues_url=get("brand.github_url") + "/issues",
            ),
            inline=False,
        )
        if ctx is not None:
            self.add_field(
                name=get("system_error.context_field"),
                value=f"```{contextify(ctx)}```",
                inline=False,
            )
        if what_failed is not None:
            self.add_field(
                name=get("system_error.what_failed_field"),
                value=f"```{what_failed}```",
                inline=False,
            )
        if reason is not None:
            reason = reason.replace(current_directory, "")
            text_fields = lines_to_container_sections(
                reason.split("\n"),
                value_max=_FIELD_VALUE_SAFE,
                line_max=_FIELD_LINE_SAFE_MAX,
            )
            for i, section in enumerate(text_fields):
                self.add_field(
                    name=fmt(
                        "system_error.reason_field", part=i + 1, total=len(text_fields)
                    ),
                    value=f"```{section}```",
                    inline=False,
                )
        self.set_footer(text=get("system_error.footer"))
