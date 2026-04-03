import random

from api.Arguments import String
from api.Bot import Bot
from api.Command import Command
from api.Game import Game
from api.MessageComponents import Button, ButtonStyle, DataTable
from api.Response import Response, ResponseType
from utils.locale import fmt, get


class TicTacToeGame(Game):
    summary = "The classic game of Xs and Os, brought to discord"
    move_command_group_description = "Commands for TicTacToe"
    description = ("Tic-Tac-Toe on Discord! The game is pretty self-explanatory,"
                   " just take turns placing Xs and Os until one player gets three in a row!")
    name = "Tic-Tac-Toe"
    player_count = 2
    moves = [Command(name="move", description="Place a piece down.",
                     options=[String(argument_name="move", description="description", autocomplete="ac_move")])]
    bots = {
        "easy": Bot(description="Picks a random legal move", callback="bot_easy"),
        "medium": Bot(description="Tries to win or block; otherwise picks center or random", callback="bot_medium"),
        "hard": Bot(description="Never misses a winning move", callback="bot_hard"),
    }
    author = "@quantumbagel"
    version = "1.0"
    author_link = "https://github.com/quantumbagel"
    source_link = "https://github.com/PlayCord/bot/blob/main/games/TicTacToeV2.py"
    time = "2min"
    difficulty = "Literally Braindead"

    def __init__(self, players):

        # Initial state information
        self.players = players
        self.x = self.players[0]
        self.o = self.players[1]
        self.size = 3

        # Dynamically updated information
        self.board = [[BoardCell() for _ in range(self.size)] for _ in range(self.size)]
        self.turn = 0
        self.row_count = [0 for _ in range(self.size)]
        self.column_count = [0 for _ in range(self.size)]
        self.diagonal_count = 0
        self.anti_diagonal_count = 0

    def state(self):
        buttons = []
        for col in range(3):
            for row in range(3):
                name = None
                emoji = None
                if self.board[row][col].id == self.x.id:
                    emoji = "❌"
                elif self.board[row][col].id == self.o.id:
                    emoji = "⭕"

                if emoji == "❌":
                    color = ButtonStyle.blurple
                elif emoji == "⭕":
                    color = ButtonStyle.green
                else:
                    color = ButtonStyle.gray

                button = Button(label=name, emoji=emoji, callback=self.move, row=row, style=color,
                                arguments={"move": str(col) + str(row)})
                buttons.append(button)
        return_this = [DataTable({self.x: {"Team:": ":x:"}, self.o: {"Team:": ":o:"}})]
        return_this.extend(buttons)

        return return_this

    def current_turn(self):
        return self.players[self.turn]

    def ac_move(self, player):
        moves = []
        all_moves = {'00': 'Top Left', '01': 'Top Mid', '02': 'Top Right', '10': 'Mid Left', '11': 'Mid Mid',
                     '12': 'Mid Right', '20': 'Bottom Left', '21': 'Bottom Mid', '22': 'Bottom Right'}
        for row in range(self.size):
            for column in range(self.size):
                if self.board[row][column].id is None:
                    label_key = str(row) + str(column)
                    label = all_moves.get(label_key, label_key)
                    # Use the game's internal move encoding: column + row
                    move_value = str(column) + str(row)
                    moves.append({label: move_value})
        return moves

    def move(self, player, move):
        if player.id != self.players[self.turn].id:
            return Response(content="It's not your turn.", style=ResponseType.error, ephemeral=True, delete_after=5)
        if self.board[int(move[1])][int(move[0])].id is not None:
            return Response(content="That tile is already taken.", style=ResponseType.error, ephemeral=True,
                            delete_after=5)
        self.board[int(move[1])][int(move[0])].take(self.players[self.turn])
        self.turn += 1
        if self.turn == len(self.players):
            self.turn = 0

    def _available_moves(self) -> list[str]:
        moves = []
        for row in range(self.size):
            for column in range(self.size):
                if self.board[row][column].id is None:
                    moves.append(str(column) + str(row))
        return moves

    def _find_winning_move(self, player_id: int) -> str | None:
        for move in self._available_moves():
            col, row = int(move[0]), int(move[1])
            self.board[row][col].id = player_id
            self.board[row][col].owner = next((p for p in self.players if p.id == player_id), None)
            won = self.outcome()
            self.board[row][col].id = None
            self.board[row][col].owner = None
            if won is not None:
                if isinstance(won, list):
                    continue
                if won.id == player_id:
                    return move
        return None

    def bot_easy(self, player):
        available = self._available_moves()
        if not available:
            return None
        return {"name": "move", "arguments": {"move": random.choice(available)}}

    def bot_medium(self, player):
        """
        Medium bot: tries to win, then block, then take center, otherwise random.
        """
        available = self._available_moves()
        if not available:
            return None

        # Win if possible
        winning_move = self._find_winning_move(player.id)
        if winning_move is not None:
            return {"name": "move", "arguments": {"move": winning_move}}

        # Block opponent's winning move
        opponents = [p for p in self.players if p.id != player.id]
        for opponent in opponents:
            block_move = self._find_winning_move(opponent.id)
            if block_move is not None:
                return {"name": "move", "arguments": {"move": block_move}}

        # Prefer center
        if "11" in available:
            return {"name": "move", "arguments": {"move": "11"}}

        # Else random
        return {"name": "move", "arguments": {"move": random.choice(available)}}

    def bot_hard(self, player):
        available = self._available_moves()
        if not available:
            return None

        winning_move = self._find_winning_move(player.id)
        if winning_move is not None:
            return {"name": "move", "arguments": {"move": winning_move}}

        opponents = [p for p in self.players if p.id != player.id]
        for opponent in opponents:
            block_move = self._find_winning_move(opponent.id)
            if block_move is not None:
                return {"name": "move", "arguments": {"move": block_move}}

        if self.board[1][1].id is None:
            return {"name": "move", "arguments": {"move": "11"}}

        corners = [m for m in ["00", "02", "20", "22"] if m in available]
        if corners:
            return {"name": "move", "arguments": {"move": random.choice(corners)}}

        return {"name": "move", "arguments": {"move": random.choice(available)}}

    def match_summary(self, outcome):
        filled = sum(1 for row in self.board for cell in row if cell.id is not None)
        if isinstance(outcome, Player):
            return fmt("game_summary.tictactoe.win", moves=filled)
        if isinstance(outcome, list):
            return get("game_summary.tictactoe.draw")
        return None

    def outcome(self):
        # Check rows
        for row in self.board:
            if row[0].id is not None and all(cell.id == row[0].id for cell in row):
                return row[0].owner  # Return the winner's owner

        # Check columns
        for col in range(3):
            if (self.board[0][col].id is not None and
                    all(self.board[row][col].id == self.board[0][col].id for row in range(3))):
                return self.board[0][col].owner  # Return the winner's owner

        # Check diagonals
        if self.board[0][0].id is not None and all(self.board[i][i].id == self.board[0][0].id for i in range(3)):
            return self.board[0][0].owner  # Return the winner's owner
        if self.board[0][2].id is not None and all(self.board[i][2 - i].id == self.board[0][2].id for i in range(3)):
            return self.board[0][2].owner  # Return the winner's owner

        # Check for a draw (self.board is full and no winner)
        if all(cell.id is not None for row in self.board for cell in row):
            # Collect all unique IDs from the self.board
            ids = [[self.players[0], self.players[1]]]
            return ids  # Return list of both IDs


class BoardCell:
    """Represents a cell on the game board that can be owned by a player."""

    def __init__(self, player=None):
        if player is not None:
            self.id = player.id
        else:
            self.id = None
        self.owner = player

    def take(self, player):
        self.id = player.id
        self.owner = player

    def __repr__(self):
        return f"BoardCell(id={self.id})"

    def __eq__(self, other):
        if other is None:
            return False
        return self.id == other.id
