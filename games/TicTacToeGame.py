import random

from cairosvg import svg2png

from utils import Player
from utils.GameStateTypes import GameStateType, ImageType, FieldType, InfoRows
from utils.InputTypes import String
from utils.Property import Property
import svg

class TicTacToeGame:
    command_description = "The classic game of Xs and Os, brought to discord"
    description = ("Tic-Tac-Toe on Discord! The game is pretty self-explanatory,"
                   " just take turns placing Xs and Os until one player gets three in a row!")
    name = "Tic-Tac-Toe"
    players = 2
    options = [String("where to play", "move", autocomplete="ac_move")]
    author = "@quantumbagel"
    version = "1.0"
    author_link = "https://github.com/quantumbagel"
    source_link = "https://github.com/quantumbagel/PlayCord/blob/main/games/TicTacToeGame.py"
    time = "2min"
    difficulty = "Literally Braindead"


    def __init__(self, players):

        # Initial state information
        self.players = players
        self.x = self.players[0]
        self.o = self.players[1]
        self.size = 3

        # Dynamically updated information
        self.board = [[Property() for _ in range(self.size)] for _ in range(self.size)]
        self.turn = 0
        self.row_count = [0 for _ in range(self.size)]
        self.column_count = [0 for _ in range(self.size)]
        self.diagonal_count = 0
        self.anti_diagonal_count = 0
        self.last_move = None

    def state(self):
        # Define dimensions
        svg_size = 300
        cell_size = svg_size / 3
        line_color = "white"
        x_color = "blue"
        o_color = "red"

        # All SVG elements
        elements = []
        # Draw grid lines
        for i in range(1, 3):
            # Vertical line
            elements.append(
                svg.Line(x1=i * cell_size, y1=0, x2=i * cell_size, y2=svg_size, stroke=line_color, stroke_width=5))
            # Horizontal line
            elements.append(
                svg.Line(x1=0, y1=i * cell_size, x2=svg_size, y2=i * cell_size, stroke=line_color, stroke_width=5))

        # Add X and O markers based on the board positions
        for row in range(3):
            for col in range(3):
                x_pos = col * cell_size + cell_size / 2
                y_pos = row * cell_size + cell_size / 2
                if self.board[row][col] == self.x:
                    # Draw X
                    offset = cell_size / 3
                    elements.append(
                        svg.Line(x1=x_pos - offset, y1=y_pos - offset, x2=x_pos + offset, y2=y_pos + offset,
                                 stroke=x_color, stroke_width=5))
                    elements.append(
                        svg.Line(x1=x_pos + offset, y1=y_pos - offset, x2=x_pos - offset, y2=y_pos + offset,
                                 stroke=x_color, stroke_width=5))
                elif self.board[row][col] == self.o:
                    # Draw O
                    radius = cell_size / 3
                    elements.append(
                        svg.Circle(cx=x_pos, cy=y_pos, r=radius, stroke=o_color, stroke_width=5, fill="none"))

        # Build the elements into an SVG bytestring
        drawing = svg.SVG(width=svg_size, height=svg_size, elements=elements)
        # Force the bytestring into a file-like object so we can upload it.
        stuff = svg2png(bytestring=drawing.as_str())
        return [ImageType(bytes=stuff), InfoRows({self.x: {"Team": ":x:"},
                                                  self.o: {"Team": ":o:"}})]

    def current_turn(self):
        return self.players[self.turn]

    def ac_move(self, player):
        moves = []
        all_moves = {'00': 'Top Left', '01': 'Top Mid', '02': 'Top Right', '10': 'Mid Left', '11': 'Mid Mid',
                     '12': 'Mid Right', '20': 'Bottom Left', '21': 'Bottom Mid', '22': 'Bottom Right'}
        for row in range(self.size):
            for column in range(self.size):
                if self.board[row][column].id is None:
                    move_id = str(row)+str(column)
                    moves.append({all_moves[move_id]: move_id})
        return moves

    def move(self, arguments):
        move = arguments["move"]
        self.last_move = [int(move[0]), int(move[1])]
        self.board[int(move[0])][int(move[1])].take(self.players[self.turn])
        self.turn += 1
        if self.turn == len(self.players):
            self.turn = 0

    def outcome(self) -> Player:
        # Check rows
        for row in self.board:
            if row[0].id is not None and all(cell.id == row[0].id for cell in row):
                return row[0].owner  # Return the winner's owner

        # Check columns
        for col in range(3):
            if self.board[0][col].id is not None and all(self.board[row][col].id == self.board[0][col].id for row in range(3)):
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


