from playcord.domain.player import Player as DomainPlayer
from playcord.domain.rating import DEFAULT_MU, DEFAULT_SIGMA_RATIO, Rating


class Player(DomainPlayer):
    """
    Represents a player in a game.

    This class is used both for in-game player representation and for
    rating/ranking purposes with TrueSkill.
    """

    # TrueSkill default values
    DEFAULT_MU = DEFAULT_MU
    DEFAULT_SIGMA_RATIO = DEFAULT_SIGMA_RATIO  # sigma = mu * ratio
    BOT_ID_BASE = 9_000_000_000_000

    def __init__(
        self,
        mu: float = None,
        sigma: float = None,
        ranking: int = None,
        id: int = None,
        name: str = None,
        is_bot: bool = False,
        bot_difficulty: str | None = None,
    ):
        """
        Create a new Player.

        :param mu: TrueSkill mu value (skill estimate)
        :param sigma: TrueSkill sigma value (uncertainty)
        :param ranking: The player's ranking in the current game
        :param id: Discord user ID
        :param name: Player's display name
        :param is_bot: Whether this player is a bot-controlled participant
        :param bot_difficulty: Bot difficulty key, if this is a bot player
        """
        resolved_mu = mu if mu is not None else self.DEFAULT_MU
        resolved_sigma = (
            sigma if sigma is not None else resolved_mu * self.DEFAULT_SIGMA_RATIO
        )
        super().__init__(
            id=id,
            display_name=name,
            rating=Rating(mu=resolved_mu, sigma=resolved_sigma),
            is_bot=is_bot,
            bot_difficulty=bot_difficulty,
            ranking=ranking,
        )

    @property
    def mention(self) -> str:
        """Get the Discord mention string for this player."""
        return super().mention

    def __eq__(self, other) -> bool:
        if not isinstance(other, Player):
            return False
        return self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)

    def __str__(self) -> str:
        return self.mention

    def __repr__(self) -> str:
        return f"Player(id={self.id}, mu={self.mu}, sigma={self.sigma}, is_bot={self.is_bot})"

    @classmethod
    def create_bot(
        cls,
        name: str,
        difficulty: str,
        bot_index: int = 0,
        mu: float = None,
        sigma: float = None,
    ) -> "Player":
        """
        Create a bot player with a synthetic unique ID.

        :param name: Display name for the bot (for example: "Mary (Bot)")
        :param difficulty: Difficulty key used for the bot
        :param bot_index: Index for unique synthetic IDs in a game
        :param mu: Optional initial mu
        :param sigma: Optional initial sigma
        """
        return cls(
            mu=mu,
            sigma=sigma,
            ranking=None,
            id=cls.BOT_ID_BASE + bot_index,
            name=name,
            is_bot=True,
            bot_difficulty=difficulty,
        )
