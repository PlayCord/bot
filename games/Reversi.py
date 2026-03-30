from api.Arguments import Integer
from api.Command import Command
from api.Game import Game
from api.MessageComponents import DataTable, Description
from api.Player import Player
from api.Response import Response


class ReversiGame(Game):
    begin_command_description = "Claim territory by surrounding your opponent's discs."
    move_command_group_description = "Commands for Reversi"
    description = "Place discs to flank and flip your opponent's discs on an 8x8 board."
    name = "Reversi"
    players = 2
    moves = [
        Command(
            name="move",
            description="Place a disc at row and column.",
            options=[
                Integer(argument_name="row", description="Row (1-8)", min_value=1, max_value=8),
                Integer(argument_name="column", description="Column (1-8)", min_value=1, max_value=8),
            ],
            callback="place",
        )
    ]
    author = "@copilot"
    version = "1.0"
    author_link = "https://github.com/github"
    source_link = "https://github.com/PlayCord/bot/blob/main/games/Reversi.py"
    time = "8min"
    difficulty = "Medium"

    def __init__(self, players: list[Player]) -> None:
        self.players = players
        self.size = 8
        self.board: list[list[Player | None]] = [[None for _ in range(self.size)] for _ in range(self.size)]
        self.turn = 0
        self.finished = False
        self.last_action = f"{self.current_turn().mention} starts."

        mid = self.size // 2
        self.board[mid - 1][mid - 1] = self.players[1]
        self.board[mid - 1][mid] = self.players[0]
        self.board[mid][mid - 1] = self.players[0]
        self.board[mid][mid] = self.players[1]

    def state(self):
        current = self.current_turn()
        valid_count = len(self._valid_moves(current))

        if self.finished:
            status = "🏁 Game over."
        else:
            status = f"➡️ Turn: {current.mention} ({valid_count} legal moves)"

        description = f"{status}\n\n{self._render_board()}\n\n{self.last_action}"
        counts = self._disc_counts()
        table = DataTable(
            {
                self.players[0]: {"Disc:": "⚫", "Count:": counts[self.players[0]]},
                self.players[1]: {"Disc:": "⚪", "Count:": counts[self.players[1]]},
            }
        )
        return [Description(description), table]

    def current_turn(self) -> Player:
        return self.players[self.turn]

    def place(self, player: Player, row: int, column: int):
        if self.finished:
            return Response(content="This game is already over.", ephemeral=True, delete_after=5)

        if not self._valid_moves(player):
            opponent_index = (self.turn + 1) % len(self.players)
            opponent = self.players[opponent_index]
            if self._valid_moves(opponent):
                self.turn = opponent_index
                self.last_action = f"{player.mention} had no legal moves. Turn passed to {opponent.mention}."
                return Response(content="No legal moves available. Your turn was passed.", ephemeral=True, delete_after=7)
            self.finished = True
            self.last_action = "Both players are out of legal moves."
            return None

        r = row - 1
        c = column - 1
        if not (0 <= r < self.size and 0 <= c < self.size):
            return Response(content="Row/column must be between 1 and 8.", ephemeral=True, delete_after=5)
        if self.board[r][c] is not None:
            return Response(content="That tile is already occupied.", ephemeral=True, delete_after=5)

        flips = self._flips_for_move(player, r, c)
        if not flips:
            return Response(content="Illegal move. You must flip at least one disc.", ephemeral=True, delete_after=5)

        self.board[r][c] = player
        for fr, fc in flips:
            self.board[fr][fc] = player

        self.last_action = f"{player.mention} played at ({row}, {column}) and flipped {len(flips)} disc(s)."

        opponent_index = (self.turn + 1) % len(self.players)
        opponent = self.players[opponent_index]
        if self._valid_moves(opponent):
            self.turn = opponent_index
        elif self._valid_moves(player):
            self.last_action += f" {opponent.mention} has no legal move and is skipped."
        else:
            self.finished = True
        return None

    def outcome(self):
        if not self.finished:
            if self._board_full() or (
                not self._valid_moves(self.players[0]) and not self._valid_moves(self.players[1])
            ):
                self.finished = True
            else:
                return None

        counts = self._disc_counts()
        p0 = self.players[0]
        p1 = self.players[1]
        if counts[p0] > counts[p1]:
            return p0
        if counts[p1] > counts[p0]:
            return p1
        return [[p0, p1]]

    def _board_full(self) -> bool:
        return all(cell is not None for row in self.board for cell in row)

    def _disc_counts(self) -> dict[Player, int]:
        counts = {self.players[0]: 0, self.players[1]: 0}
        for row in self.board:
            for cell in row:
                if cell in counts:
                    counts[cell] += 1
        return counts

    def _valid_moves(self, player: Player) -> list[tuple[int, int]]:
        valid = []
        for r in range(self.size):
            for c in range(self.size):
                if self.board[r][c] is None and self._flips_for_move(player, r, c):
                    valid.append((r, c))
        return valid

    def _flips_for_move(self, player: Player, r: int, c: int) -> list[tuple[int, int]]:
        if self.board[r][c] is not None:
            return []

        opponent = self.players[0] if self.players[1] == player else self.players[1]
        flips = []
        directions = [
            (-1, -1), (-1, 0), (-1, 1),
            (0, -1),           (0, 1),
            (1, -1),  (1, 0),  (1, 1),
        ]
        for dr, dc in directions:
            path = []
            rr = r + dr
            cc = c + dc
            while 0 <= rr < self.size and 0 <= cc < self.size and self.board[rr][cc] == opponent:
                path.append((rr, cc))
                rr += dr
                cc += dc
            if path and 0 <= rr < self.size and 0 <= cc < self.size and self.board[rr][cc] == player:
                flips.extend(path)
        return flips

    def _render_board(self) -> str:
        symbols = {None: "🟩", self.players[0]: "⚫", self.players[1]: "⚪"}
        lines = ["   " + " ".join(str(i) for i in range(1, self.size + 1))]
        for idx, row in enumerate(self.board, start=1):
            lines.append(f"{idx} " + " ".join(symbols[cell] for cell in row))
        return "\n".join(lines)
