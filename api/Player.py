class Player:
    def __init__(self, mu: float = None, sigma: float = None,
                 ranking: int = None, id: int = None, name: str = None):
        self.mu = mu
        self.sigma = sigma
        self.id = id
        self.name = name
        self.player_data = {}
        self.ranking = ranking

    @property
    def mention(self):
        return f"<@{self.id}>"  # Don't use the potential self.user.mention because it could be an Object

    def __eq__(self, other):
        if other is None:
            return False
        return self.id == other.id

    def __hash__(self):
        return hash(self.id)

    def __str__(self):
        return self.mention

    def __repr__(self):
        return f"Player(id={self.id}, mu={self.mu}, sigma={self.sigma})"
