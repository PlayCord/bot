# TODO: more functionality than just a single number LMAO
class Property:
    def __init__(self, id=None):
        self.id = id

    def take(self, id):
        self.id = id

    def __repr__(self):
        return f"Property(id={self.id})"
