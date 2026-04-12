import random
from abc import ABC, abstractmethod
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Sized
from enum import Enum
from typing import Any, ClassVar, Iterable as TypingIterable, cast

from api.Bot import Bot
from api.Command import Command
from api.MessageComponents import Message, ThreadMessage
from api.Player import Player


def _normalize_player_count_spec(value: object) -> int | list[int] | None:
    if isinstance(value, int):
        return value
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, set):
        return sorted(value)
    return None


def resolve_player_count(game: object) -> int | list[int] | None:
    """
    Return allowed player counts for a game class/object.
    """
    resolver = getattr(game, "required_player_count", None)
    if callable(resolver):
        return _normalize_player_count_spec(resolver())

    return _normalize_player_count_spec(
        getattr(game, "player_count", None)
    )


class PlayerOrder(Enum):
    """Enum for specifying player order behavior."""
    RANDOM = "random"  # Randomize player order (default)
    PRESERVE = "preserve"  # Keep the order players joined
    CREATOR_FIRST = "creator_first"  # Creator always goes first, rest randomized
    REVERSE = "reverse"  # Reverse the join order


class RoleMode(Enum):
    """How roles relate to seating after :attr:`player_order` is applied."""

    NONE = "none"  # No roles; everyone has the same abilities (default)
    RANDOM = "random"  # Roles randomly assigned; game reveals them publicly
    CHOSEN = "chosen"  # Each player picks a role in the lobby; game reveals publicly
    SECRET = "secret"  # Roles randomly assigned; game reveals privately (state / moves)


class Game(ABC):
    """
    A generic, featureless Game object.

    Games should inherit from this class and implement the required methods.

    Class Attributes:
        summary (str): Description shown in /play command
        move_command_group_description (str): Description for move commands group
        description (str): Full description of the game
        name (str): Human-readable name of the game
        player_count (int | list[int]): Number of players allowed
        moves (list[Command]): List of move commands
        bots (dict[str, Bot]): Available bot difficulties for this game
        author (str): Game author
        version (str): Game version
        author_link (str): Link to author's page
        source_link (str): Link to source code
        time (str): Estimated game duration
        difficulty (str): Game difficulty level
        player_order (PlayerOrder): How to order players (default: RANDOM)
        role_mode (RoleMode): How roles map to seats (default: NONE)
        player_roles (tuple[str, ...] | None): Role id per seat when using roles
    """
    summary: str
    move_command_group_description: str
    description: str
    name: str
    player_count: int | list[int]
    moves: list[Command] = []
    bots: dict[str, Bot] = {}
    author: str
    version: str
    author_link: str
    source_link: str
    time: str
    difficulty: str
    player_order: PlayerOrder = PlayerOrder.RANDOM
    game_schema_version: int = 1
    # Single fallback TrueSkill parameter set used when a game class does not define explicit parameters.
    default_trueskill_parameters: ClassVar[dict[str, float]] = {
        "sigma": 1 / 6,
        "beta": 1 / 12,
        "tau": 1 / 100,
        "draw": 9 / 10,
    }
    # Canonical per-game TrueSkill parameters (sigma/beta/tau as fractions of MU, draw raw).
    trueskill_parameters: ClassVar[dict[str, float] | None] = None
    # Asymmetric games: role labels (one per seat); length must match player count when using role_mode
    player_roles: ClassVar[tuple[str, ...] | None] = None
    role_mode: ClassVar[RoleMode] = RoleMode.NONE
    # Lobby selects before start; tuple of MatchOptionSpec (see api.MatchOptions)
    customizable_options: ClassVar[tuple[Any, ...]] = ()
    # When True, any option differing from its default forces an unrated match (like adding bots)
    customization_forces_unrated_when_non_default: ClassVar[bool] = True

    @classmethod
    def validate_role_selection(cls, selections: dict[int, str]) -> bool | str:
        """
        Called before starting a CHOSEN-mode game.

        Return True if valid, or a short error string if not. Default: each entry in
        :attr:`player_roles` must be chosen exactly once (multiset match).
        """
        roles = getattr(cls, "player_roles", None)
        # If no roles are defined, validation passes
        if not roles:
            return True
        # Ensure selections is a mapping with the expected size
        if (
                not isinstance(selections, dict)
                or not isinstance(roles, Iterable)
                or not isinstance(roles, Sized)
                or len(selections) != len(roles)
        ):
            return "Each player must choose a role."
        # Prepare a stable list of roles for deterministic comparison
        list_roles = list(cast(TypingIterable[str], cast(object, roles)))
        expected = Counter(list_roles)
        chosen = Counter(selections.values())
        if expected != chosen:
            return "Each role must be picked exactly once."
        return True

    @classmethod
    def seat_players(
            cls,
            players: list[Any],
            game_type_key: str,
            selections: dict[int, str] | None = None,
    ) -> list[Any]:
        """
        Reorder lobby participants for asymmetric roles after :attr:`player_order` was applied.

        Operates on :class:`~utils.database.InternalPlayer` / :class:`api.Player.Player` objects before the game instance exists.
        """
        ordered = list(players)
        roles = getattr(cls, "player_roles", None)
        mode = getattr(cls, "role_mode", RoleMode.NONE)
        # Require roles to be a sized iterable matching player count
        if not roles or not isinstance(roles, Iterable) or not isinstance(roles, Sized) or len(roles) != len(ordered):
            return ordered

        if mode == RoleMode.NONE:
            return ordered

        if mode == RoleMode.CHOSEN:
            if not selections or not isinstance(selections, dict):
                return ordered
            by_id = {p.id: p for p in ordered}
            pools: defaultdict[str, list[Any]] = defaultdict(list)
            # Prepare a stable list of roles for deterministic iteration
            list_roles = list(cast(TypingIterable[str], cast(object, roles)))

            for pid, role_key in selections.items():
                p = by_id.get(pid)
                if p is not None:
                    pools[role_key].append(p)
            for key in pools:
                pools[key].sort(key=lambda pl: pl.id)
            try:
                # Use the prepared stable list of roles
                return [pools[r].pop(0) for r in list_roles]
            except IndexError:
                return ordered

        if mode in (RoleMode.RANDOM, RoleMode.SECRET):
            random.shuffle(ordered)
            return ordered

        return ordered

    @abstractmethod
    def __init__(self, players: list[Player]) -> None:
        """
        Create a new Game instance.
        :param players: a list of Players representing who will play the game.
        """
        raise NotImplementedError

    @abstractmethod
    def state(self) -> Message:
        """
        Return the current state of the game as a CV2 message tree.
        """
        raise NotImplementedError

    @abstractmethod
    def current_turn(self) -> Player:
        """
        Return the current Player whose turn it is.
        It is highly recommended to make this function O(1) runtime
        due to the relative frequency it is called
        :return: the Player whose turn it is.
        """
        raise NotImplementedError

    @abstractmethod
    def outcome(self) -> Player | list[list[Player]] | str:
        """
        Return the outcome of the game state.

        :return: one Player who has won the game
        :return: a list of lists representing the outcome of the game. Each index is a place ([first, second, third]),
         and the inner list represents the people who got that place
        :return: string representing an error
        """
        raise NotImplementedError

    @classmethod
    def supports_bots(cls) -> bool:
        """Return True when the game defines at least one bot difficulty."""
        return bool(getattr(cls, "bots", {}))

    @classmethod
    def required_player_count(cls) -> int | list[int] | None:
        """Return allowed player counts, including legacy metadata fallback."""
        return _normalize_player_count_spec(
            getattr(cls, "player_count", None)
        )

    def attach_replay_logger(self, log_fn: Callable[[dict], None] | None) -> None:
        """Called by GameInterface so games can log stochastic events (shuffle, RNG) to replay JSONL."""
        self._replay_log = log_fn

    def log_replay_event(self, event: dict) -> None:
        """Append a replay JSONL event (e.g. type \"rng\" / \"shuffle\") when a logger is attached."""
        fn = getattr(self, "_replay_log", None)
        if callable(fn):
            fn(event)

    def on_replay_logger_attached(self) -> None:
        """
        Called once after GameInterface attaches the replay logger (runs after Game.__init__).
        Override to log RNG/setup that happened during __init__.
        """
        pass

    def is_game_finished(self) -> bool:
        """
        Return True when :meth:`outcome` is non-None (match decided: win, draw, etc.).

        Used by :class:`~utils.interfaces.GameInterface` to reject moves after the game ends.
        """
        return self.outcome() is not None

    def match_global_summary(self, outcome: object) -> str | None:
        """
        One line for the whole match: final scoreboard, how the game ended, etc.

        Shown at the top of the game-over embed and replay viewer; stored on ``matches.metadata``.
        """
        return None

    def match_summary(self, outcome: object) -> dict[int, str] | None:
        """
        Optional per-player result lines keyed by Player.id (Discord or bot id).

        Values are short English phrases such as ``Won (4-in-a-row)`` or ``2nd place (12 chips)``.
        Include every participant when returning a dict. Define copy on the game class, not locale TOML.
        """
        return None

    def player_state(self, player: Player) -> Message | None:
        """
        Optional private state for a specific player.

        Sent ephemerally after state updates when provided by a game.
        """
        return None

    def spectator_state(self) -> Message | None:
        """
        Optional spectator-specific state.

        Returning ``None`` falls back to :meth:`state`.
        """
        return None

    def thread_messages(self) -> list[ThreadMessage]:
        """
        Additional persistent messages maintained alongside the main game message.
        """
        return []

    notify_on_turn: ClassVar[bool] = False

    def turn_notification(self, player: Player) -> str:
        return f"It's your turn, {player.mention}!"
