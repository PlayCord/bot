"""
Emoji utilities.

Provides functionality for:
- Loading emojis from configuration
- Retrieval of emojis by name (with default Unicode emoji fallbacks)
- Runtime registration of custom emojis
- Dynamically writing the emoji cache YAML file
- Purging and reuploading application emojis to Discord
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import emoji
import ruamel.yaml
from emoji import is_emoji
from PIL import Image

from playcord.infrastructure.constants import (
    EMOJI_CONFIGURATION_FILE,
    ICONS_DIR,
    LONG_SPACE_EMBED,
)
from playcord.infrastructure.logging import get_logger

if TYPE_CHECKING:
    import discord

logger = get_logger("emojis")

# Loaded emojis from configuration
emojis: dict[str, dict] = {}

# Button emojis (deprecated; map to emojis.* keys)
button_emojis: dict[str, str] = {}

# Game emojis (game slug -> emoji data dict)
game_emojis: dict[str, dict] = {}

# Runtime-registered emojis (not persisted)
runtime_emojis: dict[str, dict] = {}

initialized = False
bot_ref: discord.Client | None = None


class _IconRegistry:
    """Attribute-style access to custom icon strings (``ICONS.back``)."""

    def __getattr__(self, name: str) -> str:
        return get_icon(name)

    def __repr__(self) -> str:
        return "<IconRegistry>"


ICONS = _IconRegistry()


@dataclass(slots=True)
class EmojiSyncReport:
    """Report generated after purging and reuploading emojis to Discord."""

    deleted: int = 0
    uploaded: int = 0
    failures: list[str] = field(default_factory=list)
    aborted: bool = False

    @property
    def ok(self) -> bool:
        """Return True if the sync completed without abortion or failures."""
        return not self.aborted and not self.failures


def initialize_emojis() -> bool:
    """
    Initialize emojis from the configuration file.

    :return: True if successful, False otherwise
    """
    global emojis, button_emojis, game_emojis, initialized
    initialized = True
    emojis = {}
    game_emojis = {}
    button_emojis = {}
    config_path = Path(EMOJI_CONFIGURATION_FILE)
    try:
        with config_path.open() as emoji_file:
            config = ruamel.yaml.YAML().load(emoji_file) or {}
        emojis = config.get("emojis", {}) or {}
        game_emojis = config.get("game_emojis", {}) or {}
        button_emojis = config.get("button_emojis", {}) or {}
        logger.info(
            "Loaded %s general emojis and %s game emojis from configuration.",
            len(emojis),
            len(game_emojis),
        )
        return True
    except FileNotFoundError:
        logger.warning(
            "Emoji configuration not found at %s; using defaults.",
            EMOJI_CONFIGURATION_FILE,
        )
        return True
    except Exception as e:  # noqa: BLE001
        logger.critical("Failed to load emoji configuration: %s", e)
        return False


def apply_uploaded_ids(mapping: dict[str, int], *, clear_stale: bool = False) -> None:
    """Refresh in-memory emoji ids after a runtime upload."""
    global emojis, game_emojis
    if not initialized:
        initialize_emojis()

    if clear_stale:
        for entry in emojis.values():
            entry["id"] = 0
        for entry in game_emojis.values():
            entry["id"] = 0

    for key, emoji_id in mapping.items():
        if key in emojis:
            emojis[key]["id"] = int(emoji_id)
        elif key in game_emojis:
            game_emojis[key]["id"] = int(emoji_id)


def write_emoji_yaml(mapping: dict[str, int]) -> None:
    """Write emoji.yaml using the provided mapping of emoji keys to Discord IDs."""
    button_emojis_saved = {}
    config_path = Path(EMOJI_CONFIGURATION_FILE)
    try:
        with config_path.open() as f:
            config = ruamel.yaml.YAML().load(f) or {}
            button_emojis_saved = config.get("button_emojis", {}) or {}
    except Exception:  # noqa: BLE001
        pass

    payload = {
        "emojis": {},
        "game_emojis": {},
        "button_emojis": button_emojis_saved,
    }

    # Discover emojis dynamically from the local directory
    for path in sorted(ICONS_DIR.glob("*.webp")):
        name = path.stem
        if name.startswith("game_"):
            key = name[5:]
            is_game = True
        else:
            key = name
            is_game = False

        animated = False
        try:
            with Image.open(path) as img:
                animated = getattr(img, "is_animated", False)
        except Exception:  # noqa: BLE001
            pass

        emoji_id = mapping.get(key, 0)
        entry = {"id": emoji_id, "animated": animated}

        if is_game:
            payload["game_emojis"][key] = entry
        else:
            payload["emojis"][key] = entry

    yaml = ruamel.yaml.YAML()
    yaml.default_flow_style = False
    yaml.indent(mapping=2, sequence=4, offset=2)
    with config_path.open("w") as emoji_file:
        yaml.dump(payload, emoji_file)
    logger.info("Wrote emoji configuration to %s", EMOJI_CONFIGURATION_FILE)


async def purge_and_reupload(
    bot: discord.Client,
    icons_dir: Path | None = None,
) -> EmojiSyncReport:
    """Delete all application emojis on Discord and reupload WebP files from icons_dir."""
    report = EmojiSyncReport()
    root_dir = icons_dir or ICONS_DIR

    try:
        existing = await bot.fetch_application_emojis()
    except Exception as exc:
        report.failures.append(f"fetch application emojis: {exc}")
        logger.exception("Failed to fetch application emojis")
        return report

    for d_emoji in existing:
        try:
            await d_emoji.delete()
            report.deleted += 1
        except Exception as exc:
            report.failures.append(f"delete {getattr(d_emoji, 'name', d_emoji)!r}: {exc}")
            logger.exception("Failed to delete application emoji %r", getattr(d_emoji, "name", d_emoji))

    webp_files = sorted(root_dir.glob("*.webp"), key=lambda p: p.name)
    name_to_id: dict[str, int] = {}

    for path in webp_files:
        name = path.stem
        try:
            created = await bot.create_application_emoji(
                name=name,
                image=path.read_bytes(),
            )
            name_to_id[name] = int(created.id)
            report.uploaded += 1
        except Exception as exc:
            report.failures.append(f"upload {name}: {exc}")
            logger.exception("Failed to upload emoji %r", name)

    # Convert uploaded stems back to keys
    mapping = {
        (name.removeprefix("game_")): emoji_id
        for name, emoji_id in name_to_id.items()
    }

    apply_uploaded_ids(mapping, clear_stale=True)
    write_emoji_yaml(mapping)

    return report


async def sync_ids_from_discord(bot: discord.Client) -> dict[str, int]:
    """Fetch application emojis from Discord and refresh the local id cache."""
    try:
        remote = await bot.fetch_application_emojis()
    except Exception:
        logger.exception("Failed to fetch application emojis for id sync")
        return {}

    mapping = {
        name.removeprefix("game_"): int(d_emoji.id)
        for d_emoji in remote
        if (name := d_emoji.name) is not None
    }

    apply_uploaded_ids(mapping, clear_stale=True)
    write_emoji_yaml(mapping)
    logger.info("Synced %s application emoji id(s) from Discord.", len(mapping))

    return mapping



def get_base_emoji(name: str) -> str | None:
    """Resolve a name (like "skull", ":skull:") or raw emoji (like "💀") to a unicode emoji."""
    if is_emoji(name):
        return name
    cleaned = name
    if not cleaned.startswith(":"):
        cleaned = f":{cleaned}"
    if not cleaned.endswith(":"):
        cleaned = f"{cleaned}:"
    emojized = emoji.emojize(cleaned, language="alias")
    if is_emoji(emojized):
        return emojized
    return None


def get_emoji(name: str) -> dict | None:
    """Get emoji data by name."""
    if not initialized:
        initialize_emojis()

    if name in runtime_emojis:
        return runtime_emojis[name]

    if name in emojis:
        return emojis[name]

    if name in game_emojis:
        return game_emojis[name]

    base = get_base_emoji(name)
    if base is not None:
        return {"unicode": base, "animated": False, "id": None}

    return None


def _format_emoji_string(name: str, emoji_data: dict) -> str:
    if "unicode" in emoji_data:
        return emoji_data["unicode"]
    try:
        eid = int(emoji_data["id"])
    except (KeyError, TypeError, ValueError):
        logger.warning("Emoji %r has invalid id %r", name, emoji_data.get("id"))
        return f"[{name}]"
    if eid == 0:
        return f"[{name}]"

    if emoji_data.get("animated", False):
        return f"<a:{name}:{eid}>"
    return f"<:{name}:{eid}>"


def get_icon(name: str) -> str:
    """
    Get a custom icon string for embed text.

    Returns the bracketed name when the icon is missing, invalid, or not yet uploaded.
    """
    emoji_data = get_emoji(name)
    if emoji_data is None:
        return f"[{name}]"
    return _format_emoji_string(name, emoji_data)


def get_emoji_string(name: str) -> str:
    """
    Get a formatted emoji string for use in Discord messages.

    Falls back to a zero-width placeholder when the icon is unavailable.
    """
    if not initialized:
        initialize_emojis()

    emoji_data = get_emoji(name)
    if emoji_data is None:
        if emojis:
            logger.warning(
                "Emoji %r not found in configuration file. This emoji will not be used"
                " and a long space will fill its place.",
                name,
            )
        return LONG_SPACE_EMBED

    formatted = _format_emoji_string(name, emoji_data)
    if not formatted:
        return LONG_SPACE_EMBED
    return formatted


def get_game_emoji(game_id: str) -> str:
    """
    Get the emoji for a specific game type.

    Returns a custom game icon when configured, otherwise the generic game icon
    or an empty string.
    """
    if not initialized:
        initialize_emojis()

    entry = game_emojis.get(game_id)
    if isinstance(entry, dict):
        formatted = _format_emoji_string(f"game_{game_id}", entry)
        if formatted:
            return formatted
    elif isinstance(entry, str) and entry.strip():
        return entry.strip()

    game_icon = get_icon("game")
    if game_icon:
        return game_icon
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
    emoji_val: str | discord.PartialEmoji | None,
) -> str | discord.PartialEmoji | None:
    """
    Normalize an emoji value for discord.py UI components (buttons, selects).

    Accepts unicode emoji, <:name:id> / <a:name:id>, or discord.PartialEmoji.
    Bracket placeholders such as ``[about]`` resolve to ``None`` (label-only).
    """
    if emoji_val is None:
        return None
    # Avoid TYPE_CHECKING issues at runtime with isinstance
    if not isinstance(emoji_val, str):
        # Must be PartialEmoji or similar
        return emoji_val if getattr(emoji_val, "id", None) is not None else None
    s = emoji_val.strip()
    if not s:
        return None
    if s.startswith("[") and s.endswith("]"):
        return None
    if s.startswith("<") and s.endswith(">"):
        try:
            # Let's import discord dynamically to parse it
            import discord
            parsed = discord.PartialEmoji.from_str(s)
            if parsed is not None and parsed.id is not None:
                return parsed
        except (ValueError, TypeError, AttributeError):
            logger.debug("Invalid custom emoji markup: %r", emoji_val)
        return None
    if is_emoji(s):
        return s
    return None
