class GameState:
    def __init__(self, players):
        self.metadata = None
        self.players = []

    def get_next_player_to_move(self):
        pass

    def get_player_moves(self, uuid):
        pass

    def move(self, uuid, move):
        pass

    def won(self, uuid, last_move):
        pass
