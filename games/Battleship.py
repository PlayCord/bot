import random
import html

try:
    import cairosvg
except ImportError:
    cairosvg = None
from api.Arguments import Integer
from api.Command import Command
from api.Game import Game
from api.MessageComponents import CodeBlock, DataTable, Description, Image
from api.Player import Player
from api.Response import Response


def _svg_to_png(svg_markup: str) -> bytes | None:
    if cairosvg is None:
        return None
    return cairosvg.svg2png(bytestring=svg_markup.encode("utf-8"))


def _battleship_cell_palette(value: str) -> tuple[str, str]:
    if value == "S":
        return "#94a3b8", "S"
    if value == "X":
        return "#ef4444", "X"
    if value == "O":
        return "#e2e8f0", "•"
    return "#bfdbfe", ""


def _append_battleship_grid(
        parts: list[str],
        grid: list[list[str]],
        title: str,
        origin_x: int,
        origin_y: int,
        cell: int
) -> None:
    size = len(grid)
    board_width = size * cell

    parts.append(
        f'<text x="{origin_x + (board_width / 2)}" y="{origin_y - 14}" text-anchor="middle" '
        f'font-size="16" fill="#f8fafc">{html.escape(title)}</text>'
    )

    for index in range(size):
        x = origin_x + (index * cell) + (cell / 2)
        y = origin_y + (index * cell) + (cell / 2) + 5
        parts.append(
            f'<text x="{x}" y="{origin_y - 2}" text-anchor="middle" '
            f'font-size="13" fill="#cbd5e1">{index + 1}</text>'
        )
        parts.append(
            f'<text x="{origin_x - 10}" y="{y}" text-anchor="middle" '
            f'font-size="13" fill="#cbd5e1">{index + 1}</text>'
        )

    for row in range(size):
        for col in range(size):
            x = origin_x + (col * cell)
            y = origin_y + (row * cell)
            fill, marker = _battleship_cell_palette(grid[row][col])
            parts.append(
                f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" fill="{fill}" '
                f'stroke="#334155" stroke-width="1.2"/>'
            )
            if marker:
                parts.append(
                    f'<text x="{x + (cell / 2)}" y="{y + (cell / 2)}" text-anchor="middle" '
                    f'dominant-baseline="central" font-size="16" fill="#0f172a">{marker}</text>'
                )


def render_battleship_peek_png(own_grid: list[list[str]], shots_grid: list[list[str]]) -> bytes | None:
    size = len(own_grid)
    if size == 0 or len(shots_grid) != size:
        return None

    cell = 36
    margin = 20
    axis_pad = 24
    title_pad = 34
    board_pixels = size * cell
    gap = 38

    left_origin_x = margin + axis_pad
    origin_y = margin + title_pad + axis_pad
    right_origin_x = left_origin_x + board_pixels + gap + axis_pad

    width = right_origin_x + board_pixels + margin
    height = origin_y + board_pixels + margin

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        f'<rect width="{width}" height="{height}" fill="#0f172a"/>',
    ]

    _append_battleship_grid(parts, own_grid, "Your board", left_origin_x, origin_y, cell)
    _append_battleship_grid(parts, shots_grid, "Your shots", right_origin_x, origin_y, cell)

    parts.append("</svg>")
    return _svg_to_png("".join(parts))


class BattleshipGame(Game):
    begin_command_description = "Hunt your opponent's hidden ships."
    move_command_group_description = "Commands for Battleship"
    description = "Take turns firing at coordinates on a hidden 6x6 board."
    name = "Battleship"
    players = 2
    moves = [
        Command(
            name="fire",
            description="Fire at a coordinate.",
            options=[
                Integer(argument_name="row", description="Row (1-6)", min_value=1, max_value=6),
                Integer(argument_name="column", description="Column (1-6)", min_value=1, max_value=6),
            ],
            callback="fire",
        ),
        Command(
            name="peek",
            description="Show your board and known enemy board.",
            callback="peek",
            require_current_turn=False,
        ),
    ]
    author = "@quantumbagel"
    version = "1.0"
    author_link = "https://github.com/quantumbagel"
    source_link = "https://github.com/PlayCord/bot/blob/main/games/Battleship.py"
    time = "10min"
    difficulty = "Medium"

    def __init__(self, players: list[Player]) -> None:
        self.players = players
        self.turn = 0
        self.size = 6
        self.ship_lengths = [3, 2, 2]
        self.boards: dict[Player, list[list[str]]] = {}
        self.shots: dict[Player, list[list[str]]] = {}
        self.remaining_segments: dict[Player, int] = {}
        self.winner: Player | None = None
        self.last_action = f"{self.current_turn().mention} takes first shot."

        for player in players:
            board = [["~" for _ in range(self.size)] for _ in range(self.size)]
            self._place_random_ships(board)
            self.boards[player] = board
            self.shots[player] = [["~" for _ in range(self.size)] for _ in range(self.size)]
            self.remaining_segments[player] = sum(self.ship_lengths)

    def state(self):
        if self.winner:
            status = f"🏁 Winner: {self.winner.mention}"
        else:
            status = f"➡️ Turn: {self.current_turn().mention}"

        table = DataTable(
            {
                self.players[0]: {"Ships Left:": self.remaining_segments[self.players[0]]},
                self.players[1]: {"Ships Left:": self.remaining_segments[self.players[1]]},
            }
        )
        description = f"{status}\n\n{self.last_action}\nUse `/play battleship fire row:<1-6> column:<1-6>`."
        return [Description(description), table]

    def current_turn(self) -> Player:
        return self.players[self.turn]

    def peek(self, player: Player):
        own_grid = self.boards[player]
        shots_grid = self.shots[player]
        image_bytes = render_battleship_peek_png(own_grid, shots_grid)
        if image_bytes is None:
            own = self._render_grid(own_grid, show_ships=True)
            known = self._render_grid(shots_grid, show_ships=True)
            content = f"**Your board**\n{own}\n\n**Your shots**\n{known}"
            return Response(content=content, ephemeral=True)
        return Response(
            components=[
                Description("**Your board** (left) and **your shots** (right)."),
                Image(image_bytes),
            ],
            ephemeral=True,
        )

    def fire(self, player: Player, row: int, column: int):
        if self.winner:
            return Response(content="This game is already over.", ephemeral=True, delete_after=5)

        r = row - 1
        c = column - 1
        if not (0 <= r < self.size and 0 <= c < self.size):
            return Response(content="Row/column must be between 1 and 6.", ephemeral=True, delete_after=5)

        enemy = self.players[(self.turn + 1) % 2]
        if self.shots[player][r][c] in ("X", "O"):
            return Response(content="You already fired at that coordinate.", ephemeral=True, delete_after=5)

        hit = self.boards[enemy][r][c] == "S"
        if hit:
            self.shots[player][r][c] = "X"
            self.boards[enemy][r][c] = "X"
            self.remaining_segments[enemy] -= 1
            self.last_action = f"{player.mention} fired at ({row}, {column}) and hit!"
            if self.remaining_segments[enemy] <= 0:
                self.winner = player
                self.last_action += f" {enemy.mention}'s fleet is sunk."
                return None
        else:
            self.shots[player][r][c] = "O"
            self.last_action = f"{player.mention} fired at ({row}, {column}) and missed."

        self.turn = (self.turn + 1) % len(self.players)
        return None

    def outcome(self):
        if self.winner:
            return self.winner
        return None

    def _place_random_ships(self, board: list[list[str]]) -> None:
        for length in self.ship_lengths:
            placed = False
            while not placed:
                horizontal = random.choice([True, False])
                if horizontal:
                    r = random.randint(0, self.size - 1)
                    c = random.randint(0, self.size - length)
                    if all(board[r][c + i] == "~" for i in range(length)):
                        for i in range(length):
                            board[r][c + i] = "S"
                        placed = True
                else:
                    r = random.randint(0, self.size - length)
                    c = random.randint(0, self.size - 1)
                    if all(board[r + i][c] == "~" for i in range(length)):
                        for i in range(length):
                            board[r + i][c] = "S"
                        placed = True

    def _render_grid(self, grid: list[list[str]], show_ships: bool = False) -> str:
        token = {"~": "🌊", "S": "🚢" if show_ships else "🌊", "X": "💥", "O": "⚪"}
        lines = ["   " + " ".join(str(i) for i in range(1, self.size + 1))]
        for i, row in enumerate(grid, start=1):
            lines.append(f"{i} " + " ".join(token[cell] for cell in row))
        return "\n".join(lines)
