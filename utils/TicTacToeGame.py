import io

from cairosvg import svg2png

from utils.TicTacToeGameState import TicTacToeGameState
import svg

class TicTacToeGame:
    description = "Tic-Tac-Toe. What else can I say?"
    minimum_players = 2
    maximum_players = 2
    def __init__(self, players):
       self.players = players
       self.x = self.players[0]
       self.o = self.players[1]
       self.game_state = TicTacToeGameState(players)

    def generate_game_picture(self):

        filename=''
        # Define dimensions
        svg_size = 300
        cell_size = svg_size / 3
        line_color = "white"
        x_color = "blue"
        o_color = "red"

        # Create an SVG canvas
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

                if self.game_state.board[row][col].uuid == self.x:
                    # Draw X
                    offset = cell_size / 3
                    elements.append(
                        svg.Line(x1=x_pos - offset, y1=y_pos - offset, x2=x_pos + offset, y2=y_pos + offset,
                                 stroke=x_color, stroke_width=5))
                    elements.append(
                        svg.Line(x1=x_pos + offset, y1=y_pos - offset, x2=x_pos - offset, y2=y_pos + offset,
                                 stroke=x_color, stroke_width=5))
                elif self.game_state.board[row][col].uuid == self.o:
                    # Draw O
                    radius = cell_size / 3
                    elements.append(
                        svg.Circle(cx=x_pos, cy=y_pos, r=radius, stroke=o_color, stroke_width=5, fill="none"))

        # Save the SVG to a file
        drawing = svg.SVG(width=svg_size, height=svg_size, elements=elements)
        stuff = svg2png(bytestring=drawing.as_str())
        image = io.BytesIO()
        image.write(stuff)
        image.seek(0)
        return image






