
from cairosvg import svg2png

from utils.InputTypes import String
from utils.Property import Property
import svg

class TicTacToeGame:
    description = "Tic-Tac-Toe. What else can I say?"
    minimum_players = 2
    maximum_players = 2
    options = [String("where to play", "move", autocomplete="ac_move")]



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

    def generate_game_picture(self):
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

                if self.board[row][col].id == self.x.id:
                    # Draw X
                    offset = cell_size / 3
                    elements.append(
                        svg.Line(x1=x_pos - offset, y1=y_pos - offset, x2=x_pos + offset, y2=y_pos + offset,
                                 stroke=x_color, stroke_width=5))
                    elements.append(
                        svg.Line(x1=x_pos + offset, y1=y_pos - offset, x2=x_pos - offset, y2=y_pos + offset,
                                 stroke=x_color, stroke_width=5))
                elif self.board[row][col].id == self.o.id:
                    # Draw O
                    radius = cell_size / 3
                    elements.append(
                        svg.Circle(cx=x_pos, cy=y_pos, r=radius, stroke=o_color, stroke_width=5, fill="none"))

        # Build the elements into a SVG bytestring
        drawing = svg.SVG(width=svg_size, height=svg_size, elements=elements)

        # Force the bytestring into a file-like object so we can upload it.
        stuff = svg2png(bytestring=drawing.as_str())
        return stuff

    def current_turn(self):
        return self.players[self.turn]

    def ac_move(self, player):
        moves = []
        all_moves = {'00': 'Top Left', '01': 'Top Mid', '02': 'Top Right', '10': 'Mid Left', '11': 'Mid Mid', '12': 'Mid Right', '20': 'Bottom Left', '21': 'Bottom Mid', '22': 'Bottom Right'}
        for row in range(self.size):
            for column in range(self.size):
                if self.board[row][column].id is None:
                    move_id = str(row)+str(column)
                    moves.append({all_moves[move_id]: move_id})
        return moves

    def valid_move(self, id, move):
        square = move["move"]
        return self.board[int(square[0])][int(square[1])].id is None

    def move(self, arguments):
        print("inner2", arguments)
        move = arguments["move"]
        self.board[int(move[0])][int(move[1])].id = id
        self.turn += 1
        if self.turn == len(self.players):
            self.turn = 0

    def outcome(self, last_move):
        row = last_move[0]
        column = last_move[1]

        self.row_count[row] += 1
        self.column_count[column] += 1
        if row == column:
            self.diagonal_count += 1
        if row + column == self.size:
            self.anti_diagonal_count += 1
        if self.row_count[row] == self.size or self.column_count[column] == self.size or self.diagonal_count == self.size or self.anti_diagonal_count == self.size:
            return True
        return False







