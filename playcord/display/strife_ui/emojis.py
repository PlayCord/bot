"""Emoji parsing, cache management, and application emoji uploading for strife_ui."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

import discord
from emoji import is_emoji

if TYPE_CHECKING:
    from collections.abc import Sequence

logger = logging.getLogger("strife_ui.emojis")


def _read_icon_files(
    icons_path: Path, supported_extensions: set[str]
) -> list[tuple[str, bytes, bool]]:
    """Read image files from a directory synchronously."""
    files: list[tuple[str, bytes, bool]] = []
    for file_path in sorted(icons_path.iterdir()):
        suffix = file_path.suffix.lower()
        if suffix in supported_extensions:
            # Check if animated (GIFs can be animated)
            animated = suffix == ".gif"
            files.append((file_path.stem, file_path.read_bytes(), animated))
    return files


class StrifeEmojiManager:
    """Manages local cache and Discord syncing for custom application emojis."""

    _default_instance: StrifeEmojiManager | None = None

    def __init__(self, cache_path: str | Path = "strife_emojis.json") -> None:
        """Initialize the emoji manager and load the local JSON cache."""
        self.cache_path = Path(cache_path)
        self.emojis: dict[str, dict[str, Any]] = {}
        self.load_cache()

    @classmethod
    def get_default(cls) -> StrifeEmojiManager:
        """Get the default StrifeEmojiManager instance."""
        if cls._default_instance is None:
            cls._default_instance = StrifeEmojiManager()
        return cls._default_instance

    @classmethod
    def set_default_cache_path(cls, path: str | Path) -> None:
        """Set the default StrifeEmojiManager cache filepath."""
        cls._default_instance = StrifeEmojiManager(path)

    def load_cache(self) -> None:
        """Load the local JSON cache containing custom emoji definitions."""
        if self.cache_path.exists():
            try:
                with self.cache_path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.emojis = data.get("emojis", {})
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to load emoji cache: %s", exc)

    def save_cache(self) -> None:
        """Save the custom emoji definitions to the local JSON cache."""
        try:
            # Ensure parent directory exists
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            with self.cache_path.open("w", encoding="utf-8") as f:
                json.dump({"emojis": self.emojis}, f, indent=2)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to save emoji cache: %s", exc)

    async def sync_emojis(
        self,
        bot: discord.Client,
        icons_dir: Path | str,
        *,
        purge: bool = True,
    ) -> dict[str, int]:
        """Purge existing and upload new application emojis from directory."""
        icons_path = Path(icons_dir)
        exists = await asyncio.to_thread(icons_path.exists)
        is_dir = await asyncio.to_thread(icons_path.is_dir)
        if not exists or not is_dir:
            err_msg = f"Icons directory does not exist: {icons_dir}"
            raise FileNotFoundError(err_msg)

        # 1. Fetch current application emojis from Discord
        try:
            existing_emojis: Sequence[discord.Emoji] = (
                await bot.fetch_application_emojis()
            )
        except Exception as exc:
            err_fetch = f"Failed to fetch application emojis: {exc}"
            raise discord.DiscordException(err_fetch) from exc

        # 2. Purge if requested
        if purge:
            for d_emoji in existing_emojis:
                try:
                    await d_emoji.delete()
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "Failed to delete application emoji %s: %s",
                        d_emoji.name,
                        exc,
                    )
            existing_emojis = []

        # 3. Read icons and upload new ones
        supported_extensions = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
        files = await asyncio.to_thread(
            _read_icon_files, icons_path, supported_extensions
        )

        uploaded_mapping: dict[str, int] = {}
        existing_names = {
            emoji.name: emoji for emoji in existing_emojis if emoji.name
        }

        for emoji_name, image_bytes, animated in files:
            if emoji_name in existing_names:
                emoji_obj = existing_names[emoji_name]
                uploaded_mapping[emoji_name] = emoji_obj.id
                self.emojis[emoji_name] = {
                    "id": emoji_obj.id,
                    "animated": emoji_obj.animated,
                }
                continue

            try:
                created = await bot.create_application_emoji(
                    name=emoji_name,
                    image=image_bytes,
                )
                uploaded_mapping[emoji_name] = created.id
                self.emojis[emoji_name] = {
                    "id": created.id,
                    "animated": created.animated or animated,
                }
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Failed to upload application emoji %s: %s",
                    emoji_name,
                    exc,
                )

        self.save_cache()
        return uploaded_mapping


def get_emoji_manager() -> StrifeEmojiManager:
    """Get the active default StrifeEmojiManager instance."""
    return StrifeEmojiManager.get_default()


def set_emoji_cache_path(path: str | Path) -> None:
    """Set the cache filepath for the default StrifeEmojiManager."""
    StrifeEmojiManager.set_default_cache_path(path)


def _resolve_numeric_emoji(emoji_input: str | int) -> discord.PartialEmoji | None:
    """Resolve raw numeric IDs to a discord.PartialEmoji."""
    if isinstance(emoji_input, int):
        return discord.PartialEmoji(id=emoji_input, name="emoji")
    if isinstance(emoji_input, str) and emoji_input.isdigit():
        return discord.PartialEmoji(id=int(emoji_input), name="emoji")
    return None


def _resolve_markup_emoji(val: str) -> discord.PartialEmoji | None:
    """Resolve custom emoji markup or name:id format to a discord.PartialEmoji."""
    if val.startswith("<") and val.endswith(">"):
        match = re.match(r"^<(a?):([a-zA-Z0-9_]+):(\d+)>$", val)
        if match:
            animated_flag, name, emoji_id = match.groups()
            return discord.PartialEmoji(
                id=int(emoji_id), name=name, animated=bool(animated_flag)
            )

    if ":" in val:
        match = re.match(r"^(a?):?([a-zA-Z0-9_]+):(\d+)$", val)
        if match:
            animated_flag, name, emoji_id = match.groups()
            return discord.PartialEmoji(
                id=int(emoji_id), name=name, animated=bool(animated_flag)
            )

    return None


def resolve_emoji(
    emoji_input: str | int | discord.Emoji | discord.PartialEmoji,
) -> str | discord.PartialEmoji:
    """
    Normalize emoji input into a Unicode emoji string or discord.PartialEmoji.

    Supports:
    - discord.Emoji / discord.PartialEmoji objects
    - Integers representing custom emoji IDs
    - Numeric strings representing custom emoji IDs (e.g. "123456789012345678")
    - Custom emoji markup strings (e.g. "<:name:id>" or "<a:name:id>")
    - Raw Unicode emoji characters (e.g. "⚙️")
    - Cached emoji keys from StrifeEmojiManager
    """
    if not emoji_input:
        err_req = "Emoji input is required for strife_ui components."
        raise ValueError(err_req)

    if isinstance(emoji_input, (discord.Emoji, discord.PartialEmoji)):
        return emoji_input

    # 1. Resolve numeric/integers
    num_resolved = _resolve_numeric_emoji(emoji_input)
    if num_resolved is not None:
        return num_resolved

    if isinstance(emoji_input, str):
        val = emoji_input.strip()
        if not val:
            err_empty = "Emoji input cannot be empty."
            raise ValueError(err_empty)

        # 2. Check custom markup
        markup_resolved = _resolve_markup_emoji(val)
        if markup_resolved is not None:
            return markup_resolved

        # 3. Check Unicode emoji
        if is_emoji(val):
            return val

        # 4. Check cached emoji keys in manager
        mgr = get_emoji_manager()
        if val in mgr.emojis:
            data = mgr.emojis[val]
            eid = data.get("id")
            if eid:
                return discord.PartialEmoji(
                    id=eid,
                    name=val,
                    animated=data.get("animated", False),
                )

        return val

    err_type = f"Unsupported emoji type: {type(emoji_input)}"
    raise TypeError(err_type)


def resolve_emoji_string(
    emoji_input: str | int | discord.Emoji | discord.PartialEmoji,
) -> str:
    """Convert resolved emoji into a string representation for embeds or messages."""
    resolved = resolve_emoji(emoji_input)
    if isinstance(resolved, discord.PartialEmoji):
        if resolved.id:
            anim = "a" if resolved.animated else ""
            name = resolved.name or "emoji"
            return f"<{anim}:{name}:{resolved.id}>"
        return resolved.name or ""
    return resolved
