from api.Arguments import Argument


class Command:
    def __init__(self, name: str, options: list[Argument], description: str,
                 require_current_turn: bool = True):

        # Save data to class
        self.name = name
        self.options = options
        self.description = description
        self.require_current_turn = require_current_turn
