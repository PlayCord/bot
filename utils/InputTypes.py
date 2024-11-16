import string

import discord.app_commands
from discord.app_commands import Choice


class InputType:
    description: str
    type: str
    name: str
    optional: bool


    def __init__(self, description, argument_name, optional, autocomplete, force_reload):
        self.description = description
        self.name = argument_name
        if not self._verify_name():
            raise TypeError('Argument name is invalid')
        self.optional = optional
        self.type = "default"
        self.autocomplete = autocomplete
        self.force_reload = force_reload

    def _verify_name(self):
        for char in self.name:
            if char not in string.ascii_lowercase+"_0123456789":
                return False
        return True

    def arguments(self):
        raise NotImplementedError("InputType doesn't work by itself!")

    def decorators(self):
        raise NotImplementedError("InputType doesn't work by itself!")



class String(InputType):

    def __init__(self, description, argument_name, optional=False, autocomplete=None, force_reload=False):
        super().__init__(description=description,
                         argument_name=argument_name,
                         optional=optional, autocomplete=autocomplete, force_reload=force_reload)
        self.type = "string"

    def arguments(self):
        return {self.name: {"type": str, "optional": self.optional}}

    def decorators(self):
        return {}

class Dropdown(InputType):

    def __init__(self, description, argument_name, options: dict, optional=False):
        super().__init__(description=description,
                         argument_name=argument_name,
                         optional=optional, autocomplete=None,
                         force_reload=False)
        self.type = "string"
        self.options = [Choice(name=option[0], value=option[1]) for option in options.items()]


    def arguments(self):
        return {self.name: {"type": Choice[str], "optional": self.optional}}

    def decorators(self):
        return {"choices": {self.name: self.options}}
