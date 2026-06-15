"""
Emoji utilities.

Provides functionality for:
- Loading emojis from configuration
- Registering custom emojis at runtime
- Getting emoji strings for use in Discord messages
- Getting button emojis for UI elements
- Getting game-specific emojis
"""

from __future__ import annotations

import discord
import ruamel.yaml
from emoji import is_emoji

from playcord.infrastructure.constants import (
    EMOJI_CONFIGURATION_FILE,
    LONG_SPACE_EMBED,
)
from playcord.infrastructure.logging import get_logger
from playcord.presentation.ui.emoji_manifest import (
    manifest_by_bucket,
    manifest_by_key,
)

logger = get_logger("emojis")

# Loaded emojis from configuration
emojis: dict[str, dict] = {}

# Button emojis (deprecated; map to emojis.* keys)
button_emojis: dict[str, str] = {}

# Game emojis (game slug -> emoji data dict)
game_emojis: dict[str, dict | str] = {}

# Runtime-registered emojis (not persisted)
runtime_emojis: dict[str, dict] = {}

initialized = False


class _IconRegistry:
    """Attribute-style access to custom icon strings (``ICONS.back``)."""

    def __getattr__(self, name: str) -> str:
        return get_icon(name)

    def __repr__(self) -> str:
        return "<IconRegistry>"


ICONS = _IconRegistry()


def _overlay_ids_from_cache(
    target: dict[str, dict],
    cached: dict,
    *,
    bucket: str,
) -> None:
    for key, entry in cached.items():
        if key not in target:
            logger.warning(
                "Ignoring unknown %s key %r in emoji id cache",
                bucket,
                key,
            )
            continue
        if not isinstance(entry, dict):
            continue
        if "id" in entry:
            try:
                target[key]["id"] = int(entry["id"])
            except (TypeError, ValueError):
                logger.warning("Invalid id for %s.%r in emoji cache", bucket, key)
        if "animated" in entry:
            target[key]["animated"] = bool(entry["animated"])


def initialize_emojis() -> bool:
    """
    Initialize emojis from the manifest, overlaying ids from the id cache.

    :return: True if successful, False otherwise
    """
    global emojis, button_emojis, game_emojis, initialized
    initialized = True
    emojis, game_emojis = manifest_by_bucket()
    button_emojis = {}
    try:
        with open(EMOJI_CONFIGURATION_FILE) as emoji_file:
            config = ruamel.yaml.YAML().load(emoji_file) or {}
        _overlay_ids_from_cache(emojis, config.get("emojis", {}), bucket="emojis")
        _overlay_ids_from_cache(
            game_emojis,
            config.get("game_emojis", {}),
            bucket="game_emojis",
        )
        button_emojis = config.get("button_emojis", {}) or {}
        logger.info(
            "Loaded %s manifest emojis (%s game) with id cache overlay.",
            len(emojis),
            len(game_emojis),
        )
        _bind_reaction_emojis()
        return True
    except FileNotFoundError:
        logger.warning(
            "Emoji id cache not found at %s; using manifest defaults (id=0).",
            EMOJI_CONFIGURATION_FILE,
        )
        _bind_reaction_emojis()
        return True
    except Exception as e:
        logger.critical(f"Failed to load emoji id cache: {e}")
        return False


def apply_uploaded_ids(mapping: dict[str, int]) -> None:
    """Refresh in-memory emoji ids after a runtime upload."""
    global emojis, game_emojis
    if not initialized:
        initialize_emojis()

    by_key = manifest_by_key()
    for key, emoji_id in mapping.items():
        asset = by_key.get(key)
        if asset is None:
            logger.warning("Ignoring uploaded id for unknown emoji key %r", key)
            continue
        bucket = game_emojis if asset.game else emojis
        bucket[key]["id"] = int(emoji_id)
    _bind_reaction_emojis()


def write_id_cache() -> None:
    """Serialize current emoji ids to the generated id cache file."""
    if not initialized:
        initialize_emojis()

    payload = {
        "emojis": emojis,
        "game_emojis": game_emojis,
        "button_emojis": button_emojis or {},
    }
    yaml = ruamel.yaml.YAML()
    yaml.default_flow_style = False
    yaml.indent(mapping=2, sequence=4, offset=2)
    with open(EMOJI_CONFIGURATION_FILE, "w") as emoji_file:
        yaml.dump(payload, emoji_file)
    logger.info("Wrote emoji id cache to %s", EMOJI_CONFIGURATION_FILE)


def _bind_reaction_emojis() -> None:
    """Use custom reaction icons when uploaded; otherwise keep constants.py defaults."""
    from playcord.infrastructure import constants

    for attr, key in (
        ("MESSAGE_COMMAND_SUCCEEDED", "success"),
        ("MESSAGE_COMMAND_FAILED", "error"),
        ("MESSAGE_COMMAND_PENDING", "pending"),
    ):
        icon = get_icon(key)
        if icon:
            setattr(constants, attr, icon)


def get_emoji(name: str) -> dict | None:
    """
    Get emoji data by name.

    :param name: The name/key of the emoji
    :return: Emoji data dict or None if not found
    """
    if not initialized:
        initialize_emojis()

    if name in runtime_emojis:
        return runtime_emojis[name]

    if name in emojis:
        return emojis[name]

    return None


def _format_emoji_string(name: str, emoji: dict) -> str:
    try:
        eid = int(emoji["id"])
    except (KeyError, TypeError, ValueError):
        logger.warning("Emoji %r has invalid id %r", name, emoji.get("id"))
        return ""
    if eid == 0:
        return ""
    if emoji.get("animated", False):
        return f"<a:{name}:{eid}>"
    return f"<:{name}:{eid}>"


def get_icon(name: str) -> str:
    """
    Get a custom icon string for embed text.

    Returns an empty string when the icon is missing or not yet uploaded (id 0).
    """
    emoji = get_emoji(name)
    if emoji is None:
        return ""
    return _format_emoji_string(name, emoji)


def get_emoji_string(name: str) -> str:
    """
    Get a formatted emoji string for use in Discord messages.

    Falls back to a zero-width placeholder when the icon is unavailable.
    """
    if not initialized:
        initialize_emojis()

    emoji = get_emoji(name)
    if emoji is None:
        if emojis:
            logger.warning(
                f"Emoji {name!r} not found in configuration file. This emoji will not be used"
                f" and a long space will fill its place.",
            )
        return LONG_SPACE_EMBED

    formatted = _format_emoji_string(name, emoji)
    if not formatted:
        return LONG_SPACE_EMBED
    return formatted


def get_game_emoji(game_id: str) -> str:
    """
    Get the emoji for a specific game type.

    Returns a custom game icon when configured, otherwise the generic play icon
    or an empty string.
    """
    if not initialized:
        initialize_emojis()

    entry = game_emojis.get(game_id)
    if isinstance(entry, dict):
        formatted = _format_emoji_string(game_id, entry)
        if formatted:
            return formatted
    elif isinstance(entry, str) and entry.strip():
        return entry.strip()

    play_icon = get_icon("play")
    if play_icon:
        return play_icon
    return ""


def icon_for_button(
    icon_key: str,
) -> str | discord.PartialEmoji | None:
    """Resolve an icon key for discord.ui.Button emoji=."""
    return parse_discord_emoji(get_icon(icon_key))


def icon_for_select_option(
    icon_key: str,
) -> str | discord.PartialEmoji | None:
    """Resolve an icon key for SelectOption emoji=."""
    return parse_discord_emoji(get_icon(icon_key))


def parse_discord_emoji(
    emoji: str | discord.PartialEmoji | None,
) -> str | discord.PartialEmoji | None:
    """
    Normalize an emoji value for discord.py UI components (buttons, selects).

    Accepts unicode emoji, <:name:id> / <a:name:id>, or discord.PartialEmoji.
    """
    if emoji is None:
        return None
    if isinstance(emoji, discord.PartialEmoji):
        return emoji
    if not isinstance(emoji, str):
        return None
    s = emoji.strip()
    if not s:
        return None
    if s.startswith("<") and s.endswith(">"):
        inner = s[1:-1]
        animated = inner.startswith("a:")
        body = inner[2:] if animated else inner
        parts = body.split(":")
        if len(parts) >= 2:
            try:
                name, eid = parts[0], int(parts[-1])
                return discord.PartialEmoji(name=name, id=eid, animated=animated)
            except (ValueError, TypeError):
                logger.debug("Invalid custom emoji markup: %r", emoji)
                return None
        return None
    if is_emoji(s):
        return s
    from_str = getattr(discord.PartialEmoji, "from_str", None)
    if callable(from_str):
        try:
            pe = from_str(s)
            if pe is not None and pe.id is not None:
                return pe
        except (ValueError, TypeError, AttributeError):
            pass
    return None
