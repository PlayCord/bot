from api.Arguments import Argument


class Command:
    def __init__(
        self,
        name: str,
        options: list[Argument] = None,
        description: str = None,
        require_current_turn: bool = True,
        callback: str | None = None,
        is_game_affecting: bool = True,
    ):
        # Save data to class
        self.name = name
        self.options = options
        self.description = description
        self.require_current_turn = require_current_turn
        self.callback = callback
        self.is_game_affecting = is_game_affecting
