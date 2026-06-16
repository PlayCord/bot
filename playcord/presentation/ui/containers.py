from pathlib import Path
from typing import Any

import discord

from playcord.infrastructure.constants import ERROR_COLOR, SUCCESS_COLOR
from playcord.infrastructure.locale import fmt, get
from playcord.presentation.interactions.contextify import contextify
from playcord.presentation.ui.component_kit import icon_prefix
from playcord.ui.container import (
    ContainerField,
    CustomContainer,
    TEXT_DISPLAY_MAX,
    append_container_sections,
    container_to_markdown,
    lines_to_container_sections,
)
from playcord.ui.render import container_edit_kwargs, container_send_kwargs
from playcord.ui.text import FIELD_LINE_SAFE_MAX, FIELD_VALUE_SAFE, FIELD_VALUE_MAX

MAX_EMBED_FIELDS = 25

# Public aliases for callers outside this module
chunk_text_display_lines = __import__(
    "playcord.ui.text", fromlist=["chunk_text_display_lines"]
).chunk_text_display_lines


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
                value_max=FIELD_VALUE_SAFE,
                line_max=FIELD_LINE_SAFE_MAX,
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


__all__ = [
    "ContainerField",
    "CustomContainer",
    "ErrorContainer",
    "MAX_EMBED_FIELDS",
    "SuccessContainer",
    "TEXT_DISPLAY_MAX",
    "UserErrorContainer",
    "append_container_sections",
    "chunk_text_display_lines",
    "container_edit_kwargs",
    "container_send_kwargs",
    "container_to_markdown",
    "lines_to_container_sections",
]
