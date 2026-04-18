from playcord.discord_games.arguments import Argument
from playcord.domain.game import Move


class Command(Move):
    def __init__(
        self,
        name: str,
        options: list[Argument] = None,
        description: str = None,
        require_current_turn: bool = True,
        callback: str | None = None,
        is_game_affecting: bool = True,
    ):
        super().__init__(
            name=name,
            options=tuple(options or ()),
            description=description or name,
            require_current_turn=require_current_turn,
            callback=callback,
            is_game_affecting=is_game_affecting,
        )
