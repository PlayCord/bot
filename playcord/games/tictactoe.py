"""Tic-tac-toe game."""

from __future__ import annotations

import random
from typing import TYPE_CHECKING, Any

from playcord.api import (
    BotDefinition,
    ButtonSpec,
    ButtonStyle,
    GameContext,
    GameMetadata,
    MessageLayout,
    Move,
    MoveParameter,
    Outcome,
    ParameterKind,
    ReplayableGame,
    ReplayState,
    UpsertMessage,
    handler,
)
from playcord.api.plugin import register_game
from playcord.core.errors import IllegalMove, NotPlayersTurn

if TYPE_CHECKING:
    from playcord.core.player import Player

Board = list[list[str]]
MoveCoord = tuple[int, int]

BOARD_SIZE = 3
EMPTY = " "
MARK_X = "X"
MARK_O = "O"
CENTER_MOVE = "11"

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


def _new_board() -> Board:
    return [[EMPTY for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)]


def _copy_board(board: Board) -> Board:
    return [list(row) for row in board]


class TicTacToeGame(ReplayableGame):
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
                callback=handler("bot_easy"),
            ),
            "medium": BotDefinition(
                description="Tries to win or block; otherwise picks center or random",
                callback=handler("bot_medium"),
            ),
            "hard": BotDefinition(
                description="Never misses a winning move",
                callback=handler("bot_hard"),
            ),
        },
        moves=(
            Move(
                name="move",
                description="Place a piece down.",
                callback=handler("do_move"),
                options=(
                    MoveParameter(
                        name="move",
                        description="Board position",
                        kind=ParameterKind.string,
                        autocomplete=handler("autocomplete_move"),
                    ),
                ),
                require_current_turn=True,
            ),
        ),
        peek_callback=handler("peek_status"),
    )

    def __init__(
        self,
        players: list[Player],
        *,
        match_options: dict[str, object] | None = None,
    ) -> None:
        super().__init__(players, match_options=match_options)
        self.board = _new_board()
        self.turn = 0

    def current_turn(self) -> Player | None:
        if not self.players:
            return None
        return self.players[self.turn % len(self.players)]

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
        game_outcome = self.outcome()
        board_status = self._status_line()
        buttons = self._board_buttons(self.board, game_over=game_outcome is not None)
        actions: list[UpsertMessage] = [
            UpsertMessage(
                target="thread",
                key="board",
                purpose="board",
                layout=MessageLayout(
                    content=f"{board_status}\n\n`/tictactoe move` also works.",
                    buttons=buttons,
                    button_row_width=BOARD_SIZE,
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
            msg = "It is not your turn."
            raise NotPlayersTurn(msg)

        parsed = self._parse_move(arguments.get("move", ""))
        if parsed is None:
            msg = "Choose a valid tile."
            raise IllegalMove(msg)
        col, row = parsed

        if self.board[row][col] != EMPTY:
            msg = "That tile is already taken."
            raise IllegalMove(msg)

        self.board[row][col] = self._marker_for_player(actor, self.players)
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
        values: list[tuple[str, str]] = []
        for move in self._available_moves(self.board):
            label = _MOVE_LABELS.get(move, move)
            if query and query not in label.lower() and query not in move:
                continue
            values.append((label, move))
        return values[:25]

    def bot_easy(self, player: Player, *, ctx: GameContext) -> dict[str, object] | None:
        _ = ctx
        return self._bot_move_for_difficulty(player, "easy")

    def bot_medium(
        self,
        player: Player,
        *,
        ctx: GameContext,
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
            state={"board": _new_board(), "turn": 0},
        )

    def apply_replay_event(
        self,
        state: ReplayState,
        event: dict[str, object],
    ) -> ReplayState | None:
        if event.get("type") != "move":
            return state

        args = event.get("arguments")
        if not isinstance(args, dict):
            return state

        parsed = self._parse_move(args.get("move", ""))
        if parsed is None:
            return state
        col, row = parsed

        board = self._board_from_replay_state(state.state)
        turn = self._turn_from_replay_state(state.state)
        if board[row][col] != EMPTY:
            return state

        marker = self._marker_for_replay_actor(
            state.players,
            event.get("user_id"),
            turn,
        )
        board[row][col] = marker

        next_turn = turn + 1
        if self._outcome_for_board(board) is not None:
            next_turn = turn

        move_index = self._parse_int(
            event.get("move_number", state.move_index + 1),
            default=state.move_index + 1,
        )
        return ReplayState(
            game_key=state.game_key,
            players=list(state.players),
            match_options=dict(state.match_options),
            move_index=move_index,
            state={"board": board, "turn": next_turn},
        )

    def render_replay(self, state: ReplayState) -> MessageLayout | None:
        board = self._board_from_replay_state(state.state)
        turn = self._turn_from_replay_state(state.state)
        players = state.players or self.players
        status = self._status_line_for_board(board, players, turn)
        buttons = self._board_buttons(board, disable_all=True)
        return MessageLayout(
            content=status,
            buttons=buttons,
            button_row_width=BOARD_SIZE,
        )

    def _bot_move_for_difficulty(
        self,
        player: Player,
        difficulty: str,
    ) -> dict[str, object] | None:
        available = self._available_moves(self.board)
        if not available:
            return None

        if difficulty in {"medium", "hard"}:
            if winning := self._find_winning_move(player, self.board):
                return self._move_action(winning)
            if blocking := self._find_blocking_move(player, self.board):
                return self._move_action(blocking)
            if CENTER_MOVE in available:
                return self._move_action(CENTER_MOVE)

        return self._move_action(random.choice(available))

    def _find_blocking_move(self, player: Player, board: Board) -> str | None:
        for opponent in self.players:
            if opponent.id == player.id:
                continue
            if move := self._find_winning_move(opponent, board):
                return move
        return None

    def _find_winning_move(self, player: Player, board: Board) -> str | None:
        marker = self._marker_for_player(player, self.players)
        for move in self._available_moves(board):
            parsed = self._parse_move(move)
            if parsed is None:
                continue
            col, row = parsed
            trial = _copy_board(board)
            trial[row][col] = marker
            winner = self._winning_marker(trial)
            if winner is not None and winner[0] == marker:
                return move
        return None

    def _available_moves(self, board: Board) -> list[str]:
        return [
            f"{col}{row}"
            for row in range(BOARD_SIZE)
            for col in range(BOARD_SIZE)
            if board[row][col] == EMPTY
        ]

    def _board_buttons(
        self,
        board: Board,
        *,
        disable_all: bool = False,
        game_over: bool = False,
    ) -> tuple[ButtonSpec, ...]:
        return tuple(
            ButtonSpec(
                label=board[row][col] if board[row][col] != EMPTY else "·",
                action_name="move",
                arguments={"move": f"{col}{row}"},
                style=self._button_style_for_value(board[row][col]),
                disabled=disable_all or game_over or board[row][col] != EMPTY,
                require_current_turn=not disable_all,
            )
            for row in range(BOARD_SIZE)
            for col in range(BOARD_SIZE)
        )

    def _status_line(self) -> str:
        return self._status_line_for_board(self.board, self.players, self.turn)

    def _status_line_for_board(
        self,
        board: list[list[str]],
        players: list[Player],
        turn: int,
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
        self,
        board: Board,
        players: list[Player] | None = None,
    ) -> Outcome | None:
        roster = players or self.players
        if len(roster) < 2:
            return None

        winner = self._winning_marker(board)
        if winner is not None:
            marker, reason = winner
            winner_index = 0 if marker == MARK_X else 1
            winner_player = roster[winner_index]
            loser_player = roster[1 - winner_index]
            return Outcome(
                kind="winner",
                placements=[[winner_player], [loser_player]],
                reason=reason,
            )

        if self._is_full(board):
            return Outcome(kind="draw", placements=[list(roster)])
        return None

    def _winning_marker(self, board: Board) -> tuple[str, str] | None:
        for cells, reason in _WIN_PATTERNS:
            x0, y0 = cells[0]
            marker = board[y0][x0]
            if marker == EMPTY:
                continue
            if all(board[y][x] == marker for x, y in cells):
                return marker, reason
        return None

    @staticmethod
    def _is_full(board: Board) -> bool:
        return all(cell != EMPTY for row in board for cell in row)

    def _overview_text(self, _ctx: GameContext) -> str:
        lines = [
            f"**{self.metadata.name}**",
            self._status_line(),
        ]
        return "\n".join(lines)

    @staticmethod
    def _button_style_for_value(value: str) -> ButtonStyle:
        if value == MARK_X:
            return "primary"
        if value == MARK_O:
            return "success"
        return "secondary"

    @staticmethod
    def _parse_int(value: Any, *, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _parse_move(move: object) -> MoveCoord | None:
        text = str(move).strip()
        if len(text) != 2 or not text.isdigit():
            return None

        col, row = int(text[0]), int(text[1])
        if not (0 <= row < BOARD_SIZE and 0 <= col < BOARD_SIZE):
            return None
        return col, row

    @staticmethod
    def _marker_for_player(player: Player, players: list[Player]) -> str:
        if players and player.id == players[0].id:
            return MARK_X
        return MARK_O

    def _marker_for_replay_actor(
        self,
        players: list[Player],
        actor: object,
        turn: int,
    ) -> str:
        marker = MARK_X if turn % 2 == 0 else MARK_O
        actor_id = self._parse_int(actor, default=-1)
        if players and actor_id == int(players[0].id):
            return MARK_X
        if len(players) > 1 and actor_id == int(players[1].id):
            return MARK_O
        return marker

    def _board_from_replay_state(self, raw_state: object) -> Board:
        board = _new_board()
        if not isinstance(raw_state, dict):
            return board

        raw_board = raw_state.get("board")
        if not isinstance(raw_board, list):
            return board

        for row in range(BOARD_SIZE):
            row_values: Any = raw_board[row] if row < len(raw_board) else []
            if not isinstance(row_values, list):
                continue
            for col in range(BOARD_SIZE):
                value = row_values[col] if col < len(row_values) else EMPTY
                if value in {MARK_X, MARK_O}:
                    board[row][col] = value
        return board

    def _turn_from_replay_state(self, raw_state: object) -> int:
        if not isinstance(raw_state, dict):
            return 0
        return self._parse_int(raw_state.get("turn", 0), default=0)

    @staticmethod
    def _move_action(move: str) -> dict[str, object]:
        return {"move_name": "move", "arguments": {"move": move}}


game = register_game(TicTacToeGame)

__all__ = ["TicTacToeGame", "game"]
