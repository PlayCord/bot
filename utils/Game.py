class Game:
    def __init__(self):
        self.description = None
        self.players = []
        pass

    def play(self):
        pass

    def get_next_player_to_move(self):
        return self.game_state.get_next_player_to_move()

