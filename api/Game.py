import random
from abc import ABC, abstractmethod
from collections.abc import Callable
from enum import Enum
from typing import Any, ClassVar

from api.Bot import Bot
from api.Command import Command
from api.MessageComponents import MessageComponent
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


class SeatingMode(Enum):
    """How to assign asymmetric roles after :attr:`player_order` is applied."""

    DEFAULT = "default"  # No extra reordering
    RANDOM_ROLE_ASSIGNMENT = "random_roles"  # Shuffle seats (fair random roles for asymmetric games)
    BALANCE_ROLES_BY_RATING = "balance_roles"  # 2-player: put weaker player in harder seat (see advantaged_role_index)


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
    # Optional per-game TrueSkill scale (sigma/beta/tau/draw as fractions of MU); None uses global GAME_TRUESKILL
    trueskill_scale: dict | None = None
    # Asymmetric games: role labels (one per seat); length must match player count when using seating_mode
    player_roles: ClassVar[tuple[str, ...] | None] = None
    seating_mode: ClassVar[SeatingMode] = SeatingMode.DEFAULT
    # For BALANCE_ROLES_BY_RATING (2p): seat index that is easier / advantaged (higher mu placed here)
    advantaged_role_index: ClassVar[int] = 1
    # Lobby selects before start; tuple of MatchOptionSpec (see api.MatchOptions)
    customizable_options: ClassVar[tuple[Any, ...]] = ()
    # When True, any option differing from its default forces an unrated match (like adding bots)
    customization_forces_unrated_when_non_default: ClassVar[bool] = True

    @classmethod
    def trueskill_parameters(cls, game_type_key: str) -> dict[str, float]:
        """
        Canonical TrueSkill fractions (sigma, beta, tau, draw) for this game class.

        Same values as :meth:`trueskill_fractions`; use this name when reading parameters for rating / environments.
        """
        return cls.trueskill_fractions(game_type_key)

    @classmethod
    def trueskill_fractions(cls, game_type_key: str) -> dict[str, float]:
        """
        Sigma, beta, tau (multiples of MU) and raw draw probability for this game class.

        Merges :attr:`trueskill_scale` over :data:`configuration.constants.GAME_TRUESKILL` for ``game_type_key``.
        """
        from configuration.constants import GAME_TRUESKILL

        base = dict(GAME_TRUESKILL.get(game_type_key, GAME_TRUESKILL["tictactoe"]))
        over = getattr(cls, "trueskill_scale", None)
        if over:
            base.update(over)
        return base

    @classmethod
    def seat_players(cls, players: list[Any], game_type_key: str) -> list[Any]:
        """
        Reorder lobby participants for asymmetric roles after :attr:`player_order` was applied.

        Operates on :class:`~utils.database.InternalPlayer` / :class:`api.Player.Player` objects before the game instance exists.
        """
        ordered = list(players)
        roles = getattr(cls, "player_roles", None)
        mode = getattr(cls, "seating_mode", SeatingMode.DEFAULT)
        if (
            mode == SeatingMode.DEFAULT
            or not roles
            or len(roles) != len(ordered)
        ):
            return ordered

        if mode == SeatingMode.RANDOM_ROLE_ASSIGNMENT:
            random.shuffle(ordered)
            return ordered

        if mode == SeatingMode.BALANCE_ROLES_BY_RATING and len(ordered) == 2:
            from configuration.constants import MU

            def _mu(p: Any) -> float:
                if isinstance(p, Player):
                    return float(p.mu)
                stat = getattr(p, game_type_key, None)
                if stat is not None and hasattr(stat, "mu"):
                    return float(stat.mu)
                return float(MU)

            weak, strong = sorted(ordered, key=_mu)
            adv = int(getattr(cls, "advantaged_role_index", 1))
            if adv == 0:
                return [strong, weak]
            return [weak, strong]

        random.shuffle(ordered)
        return ordered

    @abstractmethod
    def __init__(self, players: list[Player]) -> None:
        """
        Create a new Game instance.
        :param players: a list of Players representing who will play the game.
        """
        raise NotImplementedError

    @abstractmethod
    def state(self) -> list[MessageComponent]:
        """
        Return the current state of the game using MessageComponents.
        :return: a list of MessageComponents representing the game state.
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
