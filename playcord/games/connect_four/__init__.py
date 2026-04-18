"""Connect Four plugin."""

from __future__ import annotations

from playcord.domain.errors import IllegalMove, NotPlayersTurn
from playcord.domain.game import GameMetadata, Move, MoveParameter, ParameterKind
from playcord.domain.player import Player
from playcord.games.api import (
    ButtonSpec,
    GameContext,
    GamePlugin,
    MessageLayout,
    NotifyTurn,
    Outcome,
    UpsertMessage,
)
from playcord.games.plugin import RegisteredGamePlugin


class ConnectFourPlugin(GamePlugin):
    metadata = GameMetadata(
        key="connectfour",
        name="Connect Four",
        summary="Drop discs into columns and connect four in a row.",
        description="Drop your disc into a column. First to connect four discs wins.",
        move_group_description="Commands for Connect Four",
        player_count=2,
        author="@quantumbagel",
        version="2.0",
        author_link="https://github.com/quantumbagel",
        source_link="https://github.com/PlayCord/bot/blob/main/playcord/games/connect_four/__init__.py",
        time="4min",
        difficulty="Easy",
        moves=(
            Move(
                name="drop",
                description="Drop a disc into a column.",
                options=(
                    MoveParameter(
                        name="column",
                        description="Column number (1-7)",
                        kind=ParameterKind.integer,
                        min_value=1,
                        max_value=7,
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
        self.rows = 6
        self.columns = 7
        self.board = [[" " for _ in range(self.columns)] for _ in range(self.rows)]
        self.turn = 0
        self.last_action = f"{self.current_turn().mention} goes first."

    def current_turn(self) -> Player | None:
        return self.players[self.turn]

    def outcome(self) -> Outcome | None:
        for row in range(self.rows):
            for col in range(self.columns):
                symbol = self.board[row][col]
                if symbol == " ":
                    continue
                if any(
                    self._is_connected(row, col, dr, dc, symbol)
                    for dr, dc in ((1, 0), (0, 1), (1, 1), (1, -1))
                ):
                    winner = self.players[0] if symbol == "R" else self.players[1]
                    loser = self.players[1] if winner == self.players[0] else self.players[0]
                    return Outcome(kind="winner", placements=[[winner], [loser]])
        if all(cell != " " for row in self.board for cell in row):
            return Outcome(kind="draw", placements=[list(self.players)])
        return None

    def render(self, ctx: GameContext) -> tuple[UpsertMessage | NotifyTurn, ...]:
        outcome = self.outcome()
        buttons = tuple(
            ButtonSpec(
                label=str(index + 1),
                action_name="drop",
                arguments={"column": index + 1},
                disabled=self.board[0][index] != " " or outcome is not None,
            )
            for index in range(self.columns)
        )
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
                            self._board_text(),
                            "",
                            self.last_action,
                        ]
                    ),
                    buttons=buttons,
                ),
            ),
            UpsertMessage(
                target="overview",
                key="overview",
                purpose="overview",
                layout=MessageLayout(
                    content="\n".join(
                        [
                            f"**{self.metadata.name}**",
                            self._status_line(),
                            self._board_text(),
                        ]
                    )
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
        if move_name != "drop":
            raise IllegalMove(f"Unknown move {move_name!r}")
        current = self.current_turn()
        if current is None or current.id != actor.id:
            raise NotPlayersTurn("It is not your turn.")
        try:
            column = int(arguments.get("column", 0))
        except (TypeError, ValueError) as exc:
            raise IllegalMove("Column must be between 1 and 7.") from exc
        if column < 1 or column > self.columns:
            raise IllegalMove("Column must be between 1 and 7.")
        col_index = column - 1
        row_index = self._find_open_row(col_index)
        if row_index is None:
            raise IllegalMove(f"Column {column} is full.")
        self.board[row_index][col_index] = "R" if actor.id == self.players[0].id else "Y"
        self.last_action = f"{actor.mention} dropped in column {column}."
        if self.outcome() is None:
            self.turn = (self.turn + 1) % len(self.players)
        return self.render(ctx)

    def peek(self, ctx: GameContext) -> str | None:
        return f"{self._status_line()}\n{self._board_text()}"

    def _status_line(self) -> str:
        outcome = self.outcome()
        if outcome is not None:
            if outcome.kind == "winner":
                return f"Winner: {outcome.placements[0][0].mention}"
            return "Draw game."
        return f"Turn: {self.current_turn().mention}"

    def _find_open_row(self, col_index: int) -> int | None:
        for row in range(self.rows - 1, -1, -1):
            if self.board[row][col_index] == " ":
                return row
        return None

    def _board_text(self) -> str:
        mapping = {" ": "⚪", "R": "🔴", "Y": "🟡"}
        rows = [" ".join(mapping[cell] for cell in row) for row in self.board]
        rows.append("1 2 3 4 5 6 7")
        return "\n".join(rows)

    def _is_connected(self, row: int, col: int, dr: int, dc: int, symbol: str) -> bool:
        for offset in range(4):
            r = row + (dr * offset)
            c = col + (dc * offset)
            if not (0 <= r < self.rows and 0 <= c < self.columns):
                return False
            if self.board[r][c] != symbol:
                return False
        return True


plugin = RegisteredGamePlugin("connectfour", ConnectFourPlugin)

__all__ = ["ConnectFourPlugin", "plugin"]
