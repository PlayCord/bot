"""
Emoji utilities

Provides functionality for:
- Loading emojis from configuration
- Registering custom emojis at runtime
- Getting emoji strings for use in Discord messages
- Getting button emojis for UI elements
- Getting game-specific emojis
"""

import discord
import ruamel.yaml
from emoji import is_emoji

from playcord.infrastructure.app_constants import (
    EMOJI_CONFIGURATION_FILE,
    LONG_SPACE_EMBED,
)
from playcord.utils.logging_config import get_logger

logger = get_logger("emojis")

# Loaded emojis from configuration
emojis: dict[str, dict] = {}

# Button emojis (simple unicode emojis for buttons)
button_emojis: dict[str, str] = {}

# Game emojis (unicode emojis for each game type)
game_emojis: dict[str, str] = {}

# Runtime-registered emojis (not persisted)
runtime_emojis: dict[str, dict] = {}

initialized = False


def initialize_emojis() -> bool:
    """
    Initialize emojis from the configuration file.

    :return: True if successful, False otherwise
    """
    global emojis, button_emojis, game_emojis, initialized
    initialized = True
    try:
        with open(EMOJI_CONFIGURATION_FILE) as emoji_file:
            config = ruamel.yaml.YAML().load(emoji_file)
        emojis = config.get("emojis", {})
        button_emojis = config.get("button_emojis", {})
        game_emojis = config.get("game_emojis", {})
        logger.info(
            f"Loaded {len(emojis)} emojis, {len(button_emojis)} button emojis, "
            f"and {len(game_emojis)} game emojis from configuration."
        )
        return True
    except FileNotFoundError:
        logger.critical(
            f"Emoji configuration file not found: {EMOJI_CONFIGURATION_FILE}"
        )
        return False
    except Exception as e:
        logger.critical(f"Failed to load emoji configuration file: {e}")
        return False


def register_emoji(name: str, emoji_id: int, animated: bool = False) -> bool:
    """
    Register a custom emoji at runtime.

    :param name: The name/key for the emoji
    :param emoji_id: The Discord emoji ID
    :param animated: Whether the emoji is animated
    :return: True if registered successfully
    """
    if name in emojis or name in runtime_emojis:
        logger.warning(f"Emoji {name!r} already exists. Overwriting.")

    runtime_emojis[name] = {"id": emoji_id, "animated": animated}
    logger.debug(
        f"Registered runtime emoji: {name} (id={emoji_id}, animated={animated})"
    )
    return True


def unregister_emoji(name: str) -> bool:
    """
    Unregister a runtime emoji.

    :param name: The name/key of the emoji to unregister
    :return: True if unregistered, False if not found
    """
    if name in runtime_emojis:
        del runtime_emojis[name]
        logger.debug(f"Unregistered runtime emoji: {name}")
        return True
    return False


def get_emoji(name: str) -> dict | None:
    """
    Get emoji data by name.

    :param name: The name/key of the emoji
    :return: Emoji data dict or None if not found
    """
    if not initialized:
        initialize_emojis()

    # Check runtime emojis first (they can override config emojis)
    if name in runtime_emojis:
        return runtime_emojis[name]

    if name in emojis:
        return emojis[name]

    return None


def get_emoji_string(name: str) -> str:
    """
    Get a formatted emoji string for use in Discord messages.

    :param name: The name/key of the emoji
    :return: Formatted emoji string like <:name:id> or <a:name:id> for animated
    """
    if not initialized:
        initialize_emojis()

    # Check runtime emojis first
    emoji = get_emoji(name)

    if emoji is None:
        if emojis:  # Only warn if we actually have emojis loaded
            logger.warning(
                f"Emoji {name!r} not found in configuration file. This emoji will not be used"
                f" and a long space will fill its place."
            )
        return LONG_SPACE_EMBED

    try:
        eid = int(emoji["id"])
    except (KeyError, TypeError, ValueError):
        logger.warning("Emoji %r has invalid id %r", name, emoji.get("id"))
        return LONG_SPACE_EMBED

    if emoji.get("animated", False):
        return f"<a:{name}:{eid}>"
    return f"<:{name}:{eid}>"


def get_all_emojis() -> dict[str, dict]:
    """
    Get all registered emojis (config + runtime).

    :return: Dictionary of all emoji names to their data
    """
    if not initialized:
        initialize_emojis()

    # Merge with runtime emojis taking precedence
    all_emojis = {**emojis, **runtime_emojis}
    return all_emojis


def get_emoji_count() -> tuple[int, int]:
    """
    Get the count of loaded emojis.

    :return: Tuple of (config emoji count, runtime emoji count)
    """
    return len(emojis), len(runtime_emojis)


def get_button_emoji(name: str) -> str | None:
    """
    Get a button emoji by name.

    Button emojis are simple unicode emojis used for UI elements like
    join/leave/start buttons. They fall back gracefully if not configured.

    :param name: The button emoji name (e.g., 'join', 'leave', 'start')
    :return: The emoji string or None if not found
    """
    if not initialized:
        initialize_emojis()

    return button_emojis.get(name)


def get_game_emoji(game_id: str) -> str:
    """
    Get the emoji for a specific game type.

    Returns a default game emoji (🎮) if no specific emoji is configured.

    :param game_id: The game ID (e.g., 'tictactoe', 'chess')
    :return: The emoji string for the game
    """
    if not initialized:
        initialize_emojis()

    return game_emojis.get(game_id, "🎮")


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
