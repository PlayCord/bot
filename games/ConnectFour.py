from typing import Any

from api.Arguments import Integer
from api.Command import Command
from api.Game import Game
from api.MessageComponents import (
    Button,
    ButtonStyle,
    Container,
    MediaGallery,
    Message,
    TextDisplay,
    code_block,
    format_data_table_image,
)
from api.Player import Player
from api.Response import Response
from utils.svg_utils import svg_to_png


def render_connect_four_board_png(
        board: list[list[Any | None]],
        player_one: Any,
        player_two: Any
) -> bytes | None:
    rows = len(board)
    cols = len(board[0]) if rows else 0
    if rows == 0 or cols == 0:
        return None

    cell = 74
    margin = 18
    number_height = 26
    board_width = cols * cell
    board_height = rows * cell
    width = board_width + (margin * 2)
    height = board_height + (margin * 2) + number_height

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        f'<rect width="{width}" height="{height}" fill="#0f172a"/>',
        f'<rect x="{margin}" y="{margin}" width="{board_width}" height="{board_height}" '
        f'rx="16" ry="16" fill="#1d4ed8"/>',
    ]

    for row in range(rows):
        for col in range(cols):
            x = margin + (col * cell) + (cell / 2)
            y = margin + (row * cell) + (cell / 2)
            slot_color = "#f8fafc"
            cell_value = board[row][col]
            if cell_value == player_one:
                slot_color = "#ef4444"
            elif cell_value == player_two:
                slot_color = "#facc15"

            parts.append(
                f'<circle cx="{x}" cy="{y}" r="{cell * 0.36}" fill="{slot_color}" '
                f'stroke="#0f172a" stroke-width="2"/>'
            )

    for col in range(cols):
        x = margin + (col * cell) + (cell / 2)
        parts.append(
            f'<text x="{x}" y="{height - 8}" text-anchor="middle" '
            f'font-size="16" fill="#e2e8f0">{col + 1}</text>'
        )

    parts.append("</svg>")
    return svg_to_png("".join(parts))


class ConnectFourGame(Game):
    summary = "Drop discs into columns and connect four in a row."
    move_command_group_description = "Commands for Connect Four"
    description = "Drop your disc into a column. First to connect four discs wins."
    name = "Connect Four"
    player_count = 2
    trueskill_parameters = {"sigma": 1 / 6, "beta": 1 / 12, "tau": 1 / 120, "draw": 1 / 10}
    moves = [
        Command(
            name="drop",
            description="Drop a disc into a column.",
            options=[
                Integer(
                    argument_name="column",
                    description="Column number (1-7)",
                    min_value=1,
                    max_value=7,
                )
            ],
            callback="drop",
        )
    ]
    author = "@quantumbagel"
    version = "1.0"
    author_link = "https://github.com/quantumbagel"
    source_link = "https://github.com/PlayCord/bot/blob/main/games/ConnectFour.py"
    time = "4min"
    difficulty = "Easy"

    def __init__(self, players: list[Player]) -> None:
        self.players = players
        self.rows = 6
        self.columns = 7
        self.board: list[list[Player | None]] = [[None for _ in range(self.columns)] for _ in range(self.rows)]
        self.turn = 0
        self.move_count = 0
        self.winner: Player | None = None
        self.last_action = f"{self.current_turn().mention} goes first."

    def state(self) -> Message:
        if self.winner is not None:
            status = f"🏁 Winner: {self.winner.mention}"
        elif self.move_count == self.rows * self.columns:
            status = "🤝 Draw game."
        else:
            status = f"➡️ Turn: {self.current_turn().mention}"

        description = f"{status}\n\n{self.last_action}"
        buttons = []
        for col in range(self.columns):
            disabled = self.board[0][col] is not None or self.winner is not None
            buttons.append(
                Button(
                    label=str(col + 1),
                    callback=self.drop_button,
                    row=0,
                    style=ButtonStyle.gray,
                    arguments={"column": col + 1},
                    disabled=disabled,
                )
            )

        body_children = [
            TextDisplay(description),
            MediaGallery(
                format_data_table_image(
                    {
                        self.players[0]: {"Disc": "🔴"},
                        self.players[1]: {"Disc": "🟡"},
                    }
                )
            ),
        ]
        board_png = render_connect_four_board_png(self.board, self.players[0], self.players[1])
        if board_png is not None:
            body_children.append(MediaGallery(board_png))
        else:
            body_children.append(TextDisplay(code_block(self._render_board())))

        return Message(
            Container(*body_children),
            *buttons,
        )

    def current_turn(self) -> Player:
        return self.players[self.turn]

    def drop_button(self, player: Player, column: int):
        return self.drop(player, column)

    def drop(self, player: Player, column: int):
        if self.winner is not None:
            return Response(content="This game is already over.", ephemeral=True, delete_after=5)

        if player != self.current_turn():
            return Response(content="It's not your turn.", ephemeral=True, delete_after=5)

        if column < 1 or column > self.columns:
            return Response(content="Column must be between 1 and 7.", ephemeral=True, delete_after=5)

        col_index = column - 1
        row_index = self._find_open_row(col_index)
        if row_index is None:
            return Response(content=f"Column {column} is full.", ephemeral=True, delete_after=5)

        self.board[row_index][col_index] = player
        self.move_count += 1

        if self._is_winning_move(row_index, col_index, player):
            self.winner = player
            self.last_action = f"{player.mention} dropped in column {column} and connected four."
            return None

        if self.move_count == self.rows * self.columns:
            self.last_action = f"{player.mention} dropped in column {column}. The board is full."
            return None

        self.turn = (self.turn + 1) % len(self.players)
        self.last_action = f"{player.mention} dropped in column {column}."
        return None

    def outcome(self):
        if self.winner is not None:
            return self.winner
        if self.move_count == self.rows * self.columns:
            return [[self.players[0], self.players[1]]]
        return None

    def match_global_summary(self, outcome):
        if self.winner is not None:
            return f"4-in-a-row — {self.winner.mention} wins · {self.move_count} moves"
        if isinstance(outcome, list):
            return f"Draw — full board · {self.move_count} moves"
        return None

    def match_summary(self, outcome):
        detail = "4-in-a-row"
        a, b = self.players[0], self.players[1]
        if self.winner is not None:
            loser = b if self.winner == a else a
            return {
                self.winner.id: f"Won ({detail})",
                loser.id: f"Lost ({detail})",
            }
        if isinstance(outcome, list):
            return {a.id: f"Draw ({detail})", b.id: f"Draw ({detail})"}
        return None

    def _find_open_row(self, col_index: int) -> int | None:
        for row in range(self.rows - 1, -1, -1):
            if self.board[row][col_index] is None:
                return row
        return None

    def _is_winning_move(self, row: int, col: int, player: Player) -> bool:
        directions = [(1, 0), (0, 1), (1, 1), (1, -1)]
        for dr, dc in directions:
            total = 1
            total += self._count_direction(row, col, dr, dc, player)
            total += self._count_direction(row, col, -dr, -dc, player)
            if total >= 4:
                return True
        return False

    def _count_direction(self, row: int, col: int, dr: int, dc: int, player: Player) -> int:
        count = 0
        r = row + dr
        c = col + dc
        while 0 <= r < self.rows and 0 <= c < self.columns and self.board[r][c] == player:
            count += 1
            r += dr
            c += dc
        return count

    def _render_board(self) -> str:
        symbols = {None: "⚪", self.players[0]: "🔴", self.players[1]: "🟡"}
        rows = [" ".join(symbols[cell] for cell in row) for row in self.board]
        return "\n".join(rows) + "\n1 2 3 4 5 6 7"
