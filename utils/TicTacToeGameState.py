from random import randint

from utils.GameState import GameState
from utils.Property import Property


class TicTacToeGameState(GameState):
    def __init__(self, players):
        super().__init__(players)
        self.size = 3
        self.board = [[Property() for _ in range(self.size)] for _ in range(self.size)]
        self.turn = 0
        self.row_count = [0 for _ in range(self.size)]
        self.column_count = [0 for _ in range(self.size)]
        self.diagonal_count = 0
        self.anti_diagonal_count = 0

    def get_next_player_to_move(self):
        return self.players[self.turn]

    def get_player_moves(self, uuid) -> dict:
        moves = {}
        row_names = ["Left", "Middle", "Right"]
        column_names = ["Top", "Middle", "Bottom"]
        for row in range(self.size):
            for column in range(self.size):
                if self.board[row][column].uuid == None:
                    moves.update({column_names[column] + row_names[row]: (row, column)})
        return moves

    def move(self, uuid, move):
        self.board[move[0]][move[1]].uuid = uuid
        self.turn += 1
        if self.turn == len(self.players):
            self.turn = 0

    def won(self, uuid, last_move):
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


