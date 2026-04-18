"""Tic-tac-toe plugin."""

from __future__ import annotations

import random

from playcord.domain.bot import BotDefinition
from playcord.domain.errors import IllegalMove, NotPlayersTurn
from playcord.domain.game import GameMetadata, Move, MoveParameter, ParameterKind
from playcord.domain.player import Player
from playcord.games.api import (
    ButtonSpec,
    GameContext,
    GamePlugin,
    MessageLayout,
    Outcome,
    UpsertMessage,
)
from playcord.games.plugin import RegisteredGamePlugin

_MOVE_LABELS = {
    "00": "Top Left",
    "10": "Top Mid",
    "20": "Top Right",
    "01": "Mid Left",
    "11": "Center",
    "21": "Mid Right",
    "02": "Bottom Left",
    "12": "Bottom Mid",
    "22": "Bottom Right",
}


class TicTacToePlugin(GamePlugin):
    metadata = GameMetadata(
        key="tictactoe",
        name="Tic-Tac-Toe",
        summary="The classic game of Xs and Os, brought to Discord.",
        description="Take turns placing X and O until one player gets three in a row.",
        move_group_description="Commands for TicTacToe",
        player_count=2,
        author="@quantumbagel",
        version="2.0",
        author_link="https://github.com/quantumbagel",
        source_link="https://github.com/PlayCord/bot/blob/main/playcord/games/tictactoe/__init__.py",
        time="2min",
        difficulty="Easy",
        bots={
            "easy": BotDefinition(
                description="Picks a random legal move",
                callback="bot_easy",
            ),
            "medium": BotDefinition(
                description="Tries to win or block; otherwise picks center or random",
                callback="bot_medium",
            ),
            "hard": BotDefinition(
                description="Never misses a winning move",
                callback="bot_hard",
            ),
        },
        moves=(
            Move(
                name="move",
                description="Place a piece down.",
                options=(
                    MoveParameter(
                        name="move",
                        description="Board position",
                        kind=ParameterKind.string,
                        autocomplete="move",
                    ),
                ),
                require_current_turn=True,
            ),
        ),
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

    def __init__(self, players: list[Player], *, match_options: dict | None = None) -> None:
        super().__init__(players, match_options=match_options)
        self.board = [[" " for _ in range(3)] for _ in range(3)]
        self.turn = 0

    def current_turn(self) -> Player | None:
        return self.players[self.turn]

    def outcome(self) -> Outcome | None:
        lines = []
        lines.extend(self.board)
        lines.extend([[self.board[r][c] for r in range(3)] for c in range(3)])
        lines.append([self.board[i][i] for i in range(3)])
        lines.append([self.board[i][2 - i] for i in range(3)])
        for line in lines:
            if line[0] != " " and all(cell == line[0] for cell in line):
                winner = self.players[0] if line[0] == "X" else self.players[1]
                loser = self.players[1] if winner == self.players[0] else self.players[0]
                return Outcome(kind="winner", placements=[[winner], [loser]])
        if all(cell != " " for row in self.board for cell in row):
            return Outcome(kind="draw", placements=[list(self.players)])
        return None

    def render(self, ctx: GameContext) -> tuple[UpsertMessage, ...]:
        board_status = self._status_line()
        buttons = tuple(
            ButtonSpec(
                label=self.board[row][col] if self.board[row][col] != " " else "·",
                action_name="move",
                arguments={"move": f"{col}{row}"},
                style=self._button_style(row, col),
                disabled=self.board[row][col] != " " or self.outcome() is not None,
            )
            for row in range(3)
            for col in range(3)
        )
        actions: list[UpsertMessage] = [
            UpsertMessage(
                target="thread",
                key="board",
                purpose="board",
                layout=MessageLayout(
                    content=f"{board_status}\n\n`/tictactoe move` also works.",
                    buttons=buttons,
                    button_row_width=3,
                ),
            ),
            UpsertMessage(
                target="overview",
                key="overview",
                purpose="overview",
                layout=MessageLayout(content=self._overview_text(ctx)),
            ),
        ]
        return tuple(actions)

    def apply_move(
        self,
        actor: Player,
        move_name: str,
        arguments: dict[str, str],
        *,
        source: str,
        ctx: GameContext,
    ) -> tuple[UpsertMessage, ...]:
        if move_name != "move":
            raise IllegalMove(f"Unknown move {move_name!r}")
        current = self.current_turn()
        if current is None or current.id != actor.id:
            raise NotPlayersTurn("It is not your turn.")
        move = str(arguments.get("move", "")).strip()
        if len(move) != 2 or not move.isdigit():
            raise IllegalMove("Choose a valid tile.")
        col, row = int(move[0]), int(move[1])
        if not (0 <= row < 3 and 0 <= col < 3):
            raise IllegalMove("Choose a valid tile.")
        if self.board[row][col] != " ":
            raise IllegalMove("That tile is already taken.")
        self.board[row][col] = "X" if actor.id == self.players[0].id else "O"
        if self.outcome() is None:
            self.turn = (self.turn + 1) % len(self.players)
        return self.render(ctx)

    def autocomplete(
        self,
        actor: Player,
        move_name: str,
        argument_name: str,
        current: str,
        *,
        ctx: GameContext,
    ) -> list[tuple[str, str]]:
        if move_name != "move" or argument_name != "move":
            return []
        query = current.lower().strip()
        values = []
        for row in range(3):
            for col in range(3):
                if self.board[row][col] != " ":
                    continue
                move = f"{col}{row}"
                label = _MOVE_LABELS.get(move, move)
                if query and query not in label.lower() and query not in move:
                    continue
                values.append((label, move))
        return values[:25]

    def bot_move(self, player: Player, *, ctx: GameContext) -> dict[str, object] | None:
        available = self._available_moves()
        if not available:
            return None
        difficulty = player.bot_difficulty or "easy"
        if difficulty in {"medium", "hard"}:
            if winning := self._find_winning_move(player):
                return {"move_name": "move", "arguments": {"move": winning}}
            for opponent in self.players:
                if opponent.id == player.id:
                    continue
                if block := self._find_winning_move(opponent):
                    return {"move_name": "move", "arguments": {"move": block}}
            if difficulty == "hard" and "11" in available:
                return {"move_name": "move", "arguments": {"move": "11"}}
        if difficulty == "medium" and "11" in available:
            return {"move_name": "move", "arguments": {"move": "11"}}
        return {"move_name": "move", "arguments": {"move": random.choice(available)}}

    def peek(self, ctx: GameContext) -> str | None:
        return self._status_line()

    def _available_moves(self) -> list[str]:
        moves: list[str] = []
        for row in range(3):
            for col in range(3):
                if self.board[row][col] == " ":
                    moves.append(f"{col}{row}")
        return moves

    def _find_winning_move(self, player: Player) -> str | None:
        mark = "X" if player.id == self.players[0].id else "O"
        for move in self._available_moves():
            col, row = int(move[0]), int(move[1])
            self.board[row][col] = mark
            won = self.outcome()
            self.board[row][col] = " "
            if won is not None and won.kind == "winner" and won.placements[0][0].id == player.id:
                return move
        return None

    def _status_line(self) -> str:
        outcome = self.outcome()
        if outcome is not None:
            if outcome.kind == "winner":
                return f"Winner: {outcome.placements[0][0].mention}"
            return "Draw game."
        return f"Turn: {self.current_turn().mention}"

    def _overview_text(self, _ctx: GameContext) -> str:
        lines = [
            f"**{self.metadata.name}**",
            self._status_line(),
        ]
        return "\n".join(lines)

    def _button_style(self, row: int, col: int) -> str:
        value = self.board[row][col]
        if value == "X":
            return "primary"
        if value == "O":
            return "success"
        return "secondary"


plugin = RegisteredGamePlugin("tictactoe", TicTacToePlugin)

__all__ = ["TicTacToePlugin", "plugin"]
