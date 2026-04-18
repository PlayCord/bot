"""Nim plugin."""

from __future__ import annotations

from playcord.domain.errors import IllegalMove, NotPlayersTurn
from playcord.domain.game import GameMetadata, Move, MoveParameter, ParameterKind
from playcord.domain.match_options import MatchOptionSpec
from playcord.domain.player import Player
from playcord.games.api import GameContext, GamePlugin, MessageLayout, NotifyTurn, Outcome, UpsertMessage
from playcord.games.plugin import RegisteredGamePlugin


class NimPlugin(GamePlugin):
    metadata = GameMetadata(
        key="nim",
        name="Nim",
        summary="Take stones from piles. Take the last stone to win or lose in Misere.",
        description="Classic Nim with three piles. Remove stones from one pile each turn.",
        move_group_description="Commands for Nim",
        player_count=(2, 3, 4),
        author="@quantumbagel",
        version="2.0",
        author_link="https://github.com/quantumbagel",
        source_link="https://github.com/PlayCord/bot/blob/main/playcord/games/nim/__init__.py",
        time="3min",
        difficulty="Easy",
        customizable_options=(
            MatchOptionSpec(
                key="win_condition",
                label="Win rule",
                kind="choices",
                default="normal",
                choices=(
                    ("Normal - take last stone wins", "normal"),
                    ("Misere - take last stone loses (2p)", "misere"),
                ),
            ),
        ),
        moves=(
            Move(
                name="take",
                description="Take stones from a pile.",
                options=(
                    MoveParameter(
                        name="pile",
                        description="Pile number (1-3)",
                        kind=ParameterKind.integer,
                        min_value=1,
                        max_value=3,
                    ),
                    MoveParameter(
                        name="count",
                        description="Stones to remove",
                        kind=ParameterKind.integer,
                        min_value=1,
                        max_value=20,
                    ),
                ),
            ),
        ),
        notify_on_turn=True,
    )
    name = metadata.name
    summary = metadata.summary
    description = metadata.description
    move_group_description = metadata.move_group_description
    player_count = metadata.player_count
    author = metadata.author
    version = metadata.version
    author_link = metadata.author_link
    source_link = metadata.source_link
    time = metadata.time
    difficulty = metadata.difficulty
    bots = metadata.bots
    moves = metadata.moves
    customizable_options = metadata.customizable_options
    role_mode = metadata.role_mode
    player_roles = metadata.player_roles
    notify_on_turn = metadata.notify_on_turn

    def __init__(self, players: list[Player], *, match_options: dict | None = None) -> None:
        super().__init__(players, match_options=match_options)
        self.turn = 0
        self.piles = [3, 5, 7]
        self.winner: Player | None = None
        self.misere = (
            str(self.match_options.get("win_condition", "normal")) == "misere"
            and len(players) == 2
        )
        self.last_action = f"{self.current_turn().mention} starts."

    def current_turn(self) -> Player | None:
        return self.players[self.turn]

    def outcome(self) -> Outcome | None:
        if self.winner is None:
            return None
        placements = [[self.winner], [player for player in self.players if player.id != self.winner.id]]
        return Outcome(kind="winner", placements=placements)

    def render(self, ctx: GameContext) -> tuple[UpsertMessage | NotifyTurn, ...]:
        outcome = self.outcome()
        actions: list[UpsertMessage | NotifyTurn] = [
            UpsertMessage(
                target="thread",
                key="board",
                purpose="board",
                layout=MessageLayout(
                    content="\n".join(
                        [
                            self._status_line(),
                            "",
                            self._pile_text(),
                            "",
                            self.last_action,
                        ]
                    )
                ),
            ),
            UpsertMessage(
                target="overview",
                key="overview",
                purpose="overview",
                layout=MessageLayout(
                    content="\n".join([f"**{self.metadata.name}**", self._status_line(), self._pile_text()])
                ),
            ),
        ]
        current = self.current_turn()
        if outcome is None and current is not None and not current.is_bot:
            actions.append(
                NotifyTurn(
                    target="ephemeral",
                    player_id=int(current.id),
                    content=f"It's your turn, {current.mention}.",
                )
            )
        return tuple(actions)

    def apply_move(
        self,
        actor: Player,
        move_name: str,
        arguments: dict[str, object],
        *,
        source: str,
        ctx: GameContext,
    ) -> tuple[UpsertMessage | NotifyTurn, ...]:
        if move_name != "take":
            raise IllegalMove(f"Unknown move {move_name!r}")
        current = self.current_turn()
        if current is None or current.id != actor.id:
            raise NotPlayersTurn("It is not your turn.")
        try:
            pile = int(arguments.get("pile", 0))
            count = int(arguments.get("count", 0))
        except (TypeError, ValueError) as exc:
            raise IllegalMove("Choose a valid pile and stone count.") from exc
        if pile not in {1, 2, 3}:
            raise IllegalMove("Pile must be 1, 2, or 3.")
        if count < 1:
            raise IllegalMove("Count must be at least 1.")
        pile_index = pile - 1
        if self.piles[pile_index] < count:
            raise IllegalMove("That pile doesn't have enough stones.")
        self.piles[pile_index] -= count
        self.last_action = f"{actor.mention} removed {count} from pile {pile}."
        if sum(self.piles) == 0:
            if self.misere:
                self.winner = self.players[(self.turn + 1) % len(self.players)]
            else:
                self.winner = actor
        else:
            self.turn = (self.turn + 1) % len(self.players)
        return self.render(ctx)

    def peek(self, ctx: GameContext) -> str | None:
        return f"{self._status_line()}\n{self._pile_text()}"

    def _status_line(self) -> str:
        if self.winner is not None:
            suffix = " (misere)" if self.misere else ""
            return f"Winner: {self.winner.mention}{suffix}"
        suffix = " (Misere)" if self.misere else ""
        return f"Turn: {self.current_turn().mention}{suffix}"

    def _pile_text(self) -> str:
        return "\n".join(
            f"Pile {index + 1}: {'🪨' * count} ({count})" for index, count in enumerate(self.piles)
        )


plugin = RegisteredGamePlugin("nim", NimPlugin)

__all__ = ["NimPlugin", "plugin"]
