import importlib
from typing import Any

from discord import AppCommandOptionType, app_commands
from discord.app_commands import Group
from discord.app_commands.transformers import RangeTransformer

from configuration.constants import GAME_TYPES


def encode_argument(argument_name, argument_information) -> str:
    if argument_information["type"].__class__ is RangeTransformer:
        option_type = argument_information["type"]._type
        if option_type == AppCommandOptionType.integer:
            range_type = int
        elif option_type == AppCommandOptionType.string:
            range_type = str
        else:
            range_type = str
        min_value, max_value = argument_information["type"]._min, argument_information["type"]._max
        argument_type = f"app_commands.Range[{range_type.__name__}, {min_value}, {max_value}]"
    else:
        argument_type = argument_information["type"].__name__

    optional_addendum = '=None' if argument_information["optional"] else ''
    return f"{argument_name}:{argument_type}{optional_addendum}"


def encode_decorator(decorator_type, decorator_values) -> str:
    stringified_arguments = []
    for command_argument in decorator_values:
        stringified_arguments.append(f"{command_argument}={str(decorator_values[command_argument])}")
    function_arguments = ','.join(stringified_arguments)
    return f"@app_commands.{decorator_type}({function_arguments})"


def build_function_definitions() -> dict[Group, list[Any]]:
    context = {}
    for game in GAME_TYPES:
        game_class = getattr(importlib.import_module(GAME_TYPES[game][0]), GAME_TYPES[game][1])
        moves = game_class.moves
        decorators = {}
        arguments = {}

        for move in moves:
            temp_decorators = {}
            temp_arguments = {}
            if move.options is None:
                decorators[move.name] = temp_decorators
                arguments[move.name] = temp_arguments
                continue
            for option in move.options:
                option_decorators = option.decorators()
                if "autocomplete" not in option_decorators and option.autocomplete is not None:
                    option_decorators.update({"autocomplete": {option.name: "autocomplete_" + option.autocomplete}})
                option_arguments = option.arguments()
                for argument in option_arguments:
                    temp_arguments.update({argument: option_arguments[argument]})
                for decorator in option_decorators:
                    if decorator not in decorators:
                        temp_decorators[decorator] = option_decorators[decorator]
                    else:
                        temp_decorators[decorator].update({decorator: option_decorators[decorator]})
            decorators[move.name] = temp_decorators
            arguments[move.name] = temp_arguments

        dynamic_command_group = app_commands.Group(name=game, description=game_class.move_command_group_description,
                                                   guild_only=True)
        context[dynamic_command_group] = []

        for this_move in moves:
            this_move_decorators = decorators[this_move.name]
            this_move_arguments = arguments[this_move.name]

            encoded_decorators = [encode_decorator(d, this_move_decorators[d]) for d in this_move_decorators]
            encoded_arguments = [encode_argument(a, this_move_arguments[a]) for a in this_move_arguments]
            signature_arguments = ", ".join(["ctx", *encoded_arguments])
            decorator_block = "\n".join(encoded_decorators)
            if decorator_block:
                decorator_block += "\n"

            command_name = game + "_" + this_move.name
            move_command = (f"{decorator_block}"
                            f"@group.command(name='{this_move.name}', description='{this_move.description}')\n"
                            f"async def {command_name}({signature_arguments}):\n"
                            f"  await ctx.response.defer(ephemeral=True)\n"
                            f"  await handle_move(ctx=ctx, name={this_move.name!r}, arguments=locals(), current_turn_required={this_move.require_current_turn})\n")

            if "autocomplete" in this_move_decorators:
                for autocomplete in this_move_decorators["autocomplete"]:
                    ac_command_name = this_move_decorators["autocomplete"][autocomplete]
                    ac_command = (f"async def {ac_command_name}(ctx, current):\n"
                                  f"   return await handle_autocomplete(ctx, {this_move.name!r}, current, {autocomplete!r})\n")
                    context[dynamic_command_group].append(ac_command)

            context[dynamic_command_group].append(move_command)

    return context
