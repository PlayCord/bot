class Bot:
    """
    Represents a bot difficulty configuration for a game.

    Instances of this class are stored in ``Game.bots`` with the difficulty key:
    ``{"easy": Bot(...), "hard": Bot(...)}``.
    """

    def __init__(self, description: str, callback: str | None = None):
        """
        Create a bot difficulty configuration.

        :param description: Human-readable description shown in autocomplete.
        :param callback: Optional game method name used to execute a bot turn.
                         If omitted, the difficulty key itself is used.
        """
        self.description = description
        self.callback = callback
