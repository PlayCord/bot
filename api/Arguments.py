from discord.app_commands import Choice


class Argument:
    """
    An Argument is something that can be passed to a Command as an option.
    """
    def __init__(self, argument_name: str, description: str, optional: bool, autocomplete: str | None = None, force_reload: bool = True):
        """
        Create a new argument.
        :param description: description of the argument.
        :param argument_name: name of the argument.
        :param optional: whether this argument is optional
        :param autocomplete: string literal of autocomplete function, or None
        :param force_reload: whether to force reload (no autocomplete cache)
        """
        # Instantiate class variables
        self.description = description
        self.name = argument_name
        self.optional = optional
        self.type = "default"
        self.autocomplete = autocomplete
        self.force_reload = force_reload

    def arguments(self) -> dict[str, dict[str, str | bool]]:
        """
        Return the arguments as a dictionary.
        format: {name: {"type": type, "optional": optional}} -> name: [type] = [None if optional]
        :return:
        """
        pass

    def decorators(self) -> dict[str, dict[str, str]]:
        """
        Return the decorators as a dictionary
        format: {name: {key: value}} -> @app_commands.name(key=value)

        :return: the decorators as a dictionary
        """
        pass



class String(Argument):
    """
    A string argument.
    """
    def __init__(self, argument_name: str, description: str, optional: bool = False,
                 autocomplete: str | None = None, force_reload: bool = False) -> None:
        """
        Create a new string.
        :param description: description of the string argument.
        :param argument_name: name of the string argument.
        :param optional: whether this string argument is optional
        :param autocomplete: autocomplete string literal of autocomplete function, or None
        :param force_reload: whether to force reload (no autocomplete cache)
        """
        super().__init__(description=description,
                         argument_name=argument_name,
                         optional=optional, autocomplete=autocomplete, force_reload=force_reload)

        # Class arguments
        self.type = "string"

    def arguments(self) -> dict[str, dict[str, str | bool]]:
        """
        Return the arguments for this String as a dictionary.
        type=str, optional=self.optional, name=self.name
        :return: arguments as a dictionary
        """
        return {self.name: {"type": str, "optional": self.optional}}

    def decorators(self) -> dict:
        """
        String does not need to be decorated.
        :return: empty dictionary
        """
        return {}

class Dropdown(Argument):
    """
    A dropdown argument.
    """
    def __init__(self, argument_name: str, description: str, options: dict, optional: bool = False) -> None:
        """
        Create a new dropdown.
        :param description: description of the dropdown argument.
        :param argument_name: name of the dropdown argument.
        :param optional: whether this dropdown argument is optional
        """
        super().__init__(description=description,
                         argument_name=argument_name,
                         optional=optional, autocomplete=None,
                         force_reload=False)

        # Instantiate class options
        self.type = "string"
        self.options = [Choice(name=option[0], value=option[1]) for option in options.items()]


    def arguments(self) -> dict[str, dict[str, str | bool]]:
        """
        Return the arguments for this Dropdown as a dictionary.
        type=Choice[str], optional=self.optional, name=self.name
        :return: arguments as a dictionary
        """
        return {self.name: {"type": Choice[str], "optional": self.optional}}

    def decorators(self) -> dict[str, dict[str, str]]:
        """
        Dropdown needs to be decorated with @app_commands.choices(self.name=self.options)
        :return: dictionary representation of this dropdown's decorator
        """
        return {"choices": {self.name: self.options}}
