

class Player:
    def __init__(self, name, uuid, mu, sigma):
        self.mu = mu
        self.sigma = sigma
        self.name = name
        self.uuid = uuid
        self.player_data = {}
        self.moves_made = 0
        self.eliminated = False

    def move(self, new_player_data: dict):
        self.moves_made += 1
        self.player_data.update(new_player_data)


