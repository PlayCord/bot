"""Tic-tac-toe plugin."""

from __future__ import annotations

import random

from playcord.domain.bot import BotDefinition
from playcord.domain.errors import IllegalMove, NotPlayersTurn
from playcord.domain.game import GameMetadata, Move, MoveParameter, ParameterKind
from playcord.domain.player import Player
from playcord.games.api import (
    ButtonSpec,
    ButtonStyle,
    GameContext,
    GamePlugin,
    MessageLayout,
    Outcome,
    ReplayState,
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

_WIN_PATTERNS = (
    (((0, 0), (1, 0), (2, 0)), "top row"),
    (((0, 1), (1, 1), (2, 1)), "middle row"),
    (((0, 2), (1, 2), (2, 2)), "bottom row"),
    (((0, 0), (0, 1), (0, 2)), "left column"),
    (((1, 0), (1, 1), (1, 2)), "middle column"),
    (((2, 0), (2, 1), (2, 2)), "right column"),
    (((0, 0), (1, 1), (2, 2)), "main diagonal"),
    (((2, 0), (1, 1), (0, 2)), "anti-diagonal"),
)


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
                callback="do_move",
                options=(
                    MoveParameter(
                        name="move",
                        description="Board position",
                        kind=ParameterKind.string,
                        autocomplete="autocomplete_move",
                    ),
                ),
                require_current_turn=True,
            ),
        ),
        peek_callback="peek_status",
    )

    def __init__(
        self, players: list[Player], *, match_options: dict[str, object] | None = None
    ) -> None:
        super().__init__(players, match_options=match_options)
        self.board = [[" " for _ in range(3)] for _ in range(3)]
        self.turn = 0

    def current_turn(self) -> Player | None:
        return self.players[self.turn]

    def outcome(self) -> Outcome | None:
        return self._outcome_for_board(self.board)

    def match_global_summary(self, outcome: Outcome) -> str | None:
        if outcome.kind == "draw":
            return "Draw"
        if outcome.kind == "winner" and outcome.placements:
            winner = outcome.placements[0][0]
            if outcome.reason:
                return f"{winner.mention} won by taking the {outcome.reason}"
            return f"{winner.mention} won"
        if outcome.kind == "interrupted":
            return "Interrupted"
        return None

    def match_summary(self, outcome: Outcome) -> dict[int, str] | None:
        if outcome.kind == "draw":
            return {int(player.id): "Draw" for player in self.players}
        if outcome.kind == "winner" and outcome.placements:
            winners = {int(player.id) for player in outcome.placements[0]}
            return {
                int(player.id): ("Win" if int(player.id) in winners else "Loss")
                for player in self.players
            }
        if outcome.kind == "interrupted":
            return {int(player.id): "Interrupted" for player in self.players}
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

    def do_move(
        self,
        actor: Player,
        arguments: dict[str, str],
        *,
        source: str,
        ctx: GameContext,
    ) -> tuple[UpsertMessage, ...]:
        _ = source
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

    def autocomplete_move(
        self,
        actor: Player,
        current: str,
        *,
        ctx: GameContext,
    ) -> list[tuple[str, str]]:
        _ = actor
        _ = ctx
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

    def bot_easy(self, player: Player, *, ctx: GameContext) -> dict[str, object] | None:
        _ = ctx
        return self._bot_move_for_difficulty(player, "easy")

    def bot_medium(
        self, player: Player, *, ctx: GameContext
    ) -> dict[str, object] | None:
        _ = ctx
        return self._bot_move_for_difficulty(player, "medium")

    def bot_hard(self, player: Player, *, ctx: GameContext) -> dict[str, object] | None:
        _ = ctx
        return self._bot_move_for_difficulty(player, "hard")

    def peek_status(self, *, ctx: GameContext) -> str | None:
        _ = ctx
        return self._status_line()

    def initial_replay_state(self, ctx: GameContext) -> ReplayState | None:
        return ReplayState(
            game_key=ctx.game_key,
            players=list(ctx.players),
            match_options=dict(ctx.match_options),
            move_index=0,
            state={
                "board": [[" " for _ in range(3)] for _ in range(3)],
                "turn": 0,
            },
        )

    def apply_replay_event(
        self, state: ReplayState, event: dict[str, object]
    ) -> ReplayState | None:
        if event.get("type") != "move":
            return state

        raw = state.state if isinstance(state.state, dict) else {}
        board = [list(row) for row in raw.get("board", [[" "] * 3 for _ in range(3)])]
        turn_raw = raw.get("turn", 0)
        try:
            turn = int(turn_raw)
        except (TypeError, ValueError):
            turn = 0

        args = event.get("arguments")
        if not isinstance(args, dict):
            return state
        move = str(args.get("move", "")).strip()
        if len(move) != 2 or not move.isdigit():
            return state
        col, row = int(move[0]), int(move[1])
        if not (0 <= row < 3 and 0 <= col < 3):
            return state
        if board[row][col] != " ":
            return state

        marker = "X" if turn % 2 == 0 else "O"
        actor = event.get("user_id")
        if actor is not None:
            try:
                actor_id = int(actor)
            except (TypeError, ValueError):
                actor_id = None
            else:
                if state.players and actor_id == int(state.players[0].id):
                    marker = "X"
                elif len(state.players) > 1 and actor_id == int(state.players[1].id):
                    marker = "O"

        board[row][col] = marker
        next_turn = turn + 1
        if self._outcome_for_board(board) is not None:
            next_turn = turn

        move_index_raw = event.get("move_number", state.move_index + 1)
        try:
            move_index = int(move_index_raw)
        except (TypeError, ValueError):
            move_index = state.move_index + 1
        return ReplayState(
            game_key=state.game_key,
            players=list(state.players),
            match_options=dict(state.match_options),
            move_index=move_index,
            state={"board": board, "turn": next_turn},
        )

    def render_replay(self, state: ReplayState) -> MessageLayout | None:
        raw = state.state if isinstance(state.state, dict) else {}
        board = [list(row) for row in raw.get("board", [[" "] * 3 for _ in range(3)])]
        turn_raw = raw.get("turn", 0)
        try:
            turn = int(turn_raw)
        except (TypeError, ValueError):
            turn = 0
        players = state.players if state.players else self.players
        status = self._status_line_for_board(board, players, turn)
        buttons = tuple(
            ButtonSpec(
                label=board[row][col] if board[row][col] != " " else "·",
                action_name="move",
                arguments={"move": f"{col}{row}"},
                style=self._button_style_for_value(board[row][col]),
                disabled=True,
                require_current_turn=False,
            )
            for row in range(3)
            for col in range(3)
        )
        return MessageLayout(content=status, buttons=buttons, button_row_width=3)

    def _bot_move_for_difficulty(
        self, player: Player, difficulty: str
    ) -> dict[str, object] | None:
        available = self._available_moves()
        if not available:
            return None
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
            if (
                won is not None
                and won.kind == "winner"
                and won.placements[0][0].id == player.id
            ):
                return move
        return None

    def _status_line(self) -> str:
        return self._status_line_for_board(self.board, self.players, self.turn)

    def _status_line_for_board(
        self, board: list[list[str]], players: list[Player], turn: int
    ) -> str:
        outcome = self._outcome_for_board(board, players)
        if outcome is not None:
            if outcome.kind == "winner":
                return f"Winner: {outcome.placements[0][0].mention}"
            return "Draw game."
        if not players:
            return "Turn: ?"
        return f"Turn: {players[turn % len(players)].mention}"

    def _outcome_for_board(
        self, board: list[list[str]], players: list[Player] | None = None
    ) -> Outcome | None:
        roster = players or self.players
        if len(roster) < 2:
            return None
        for cells, reason in _WIN_PATTERNS:
            x0, y0 = cells[0]
            marker = board[y0][x0]
            if marker == " ":
                continue
            if all(board[y][x] == marker for x, y in cells):
                winner = roster[0] if marker == "X" else roster[1]
                loser = roster[1] if winner == roster[0] else roster[0]
                return Outcome(
                    kind="winner",
                    placements=[[winner], [loser]],
                    reason=reason,
                )
        if all(cell != " " for row in board for cell in row):
            return Outcome(kind="draw", placements=[list(roster)])
        return None

    def _overview_text(self, _ctx: GameContext) -> str:
        lines = [
            f"**{self.metadata.name}**",
            self._status_line(),
        ]
        return "\n".join(lines)

    def _button_style(self, row: int, col: int) -> ButtonStyle:
        return self._button_style_for_value(self.board[row][col])

    @staticmethod
    def _button_style_for_value(value: str) -> ButtonStyle:
        if value == "X":
            return "primary"
        if value == "O":
            return "success"
        return "secondary"


plugin = RegisteredGamePlugin("tictactoe", TicTacToePlugin)

__all__ = ["TicTacToePlugin", "plugin"]
