import random

from api.Arguments import Integer
from api.Command import Command
from api.Game import Game
from api.MessageComponents import DataTable, Description
from api.Player import Player
from api.Response import Response


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
    author = "@copilot"
    version = "1.0"
    author_link = "https://github.com/github"
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
        own = self._render_grid(self.boards[player], show_ships=True)
        known = self._render_grid(self.shots[player], show_ships=True)
        content = f"**Your board**\n{own}\n\n**Your shots**\n{known}"
        return Response(content=content, ephemeral=True)

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
