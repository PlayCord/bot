# TODO: more functionality than just a single number LMAO
# Somewhat implemented
class Property:
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
        return f"Property(id={self.id})"

    def __eq__(self, other):
        if other is None:
            return False
        return self.id == other.id
