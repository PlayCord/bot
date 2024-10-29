from utils.TicTacToeGameState import TicTacToeGameState


class TicTacToeGame:
    description = "Tic-Tac-Toe. What else can I say?"
    num_players = [2]
    def __init__(self, players):
       self.players = players
       self.game_state = TicTacToeGameState(players)





