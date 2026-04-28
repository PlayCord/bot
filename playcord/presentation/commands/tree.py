"""Programmatic app-command tree builder."""

from __future__ import annotations

import inspect
from typing import Any

import discord
from discord import app_commands

from playcord.games import GAME_BY_KEY, GAMES
from playcord.presentation.cogs.games import handle_autocomplete, handle_move
from playcord.presentation.commands.play import command_play


def _annotation_for_parameter(parameter: Any) -> Any:
    if parameter.kind.value == "integer":
        if parameter.min_value is not None and parameter.max_value is not None:
            return app_commands.Range[int, parameter.min_value, parameter.max_value]
        return int
    return str


def _choices_decorator(command: app_commands.Command[Any, ..., Any], move: Any) -> None:
    for parameter in move.options:
        command._params[parameter.name].description = parameter.description  # type: ignore[attr-defined]
        if not parameter.choices:
            continue
        choices = [
            app_commands.Choice(name=label, value=value)
            for label, value in parameter.choices
        ]
        command._params[parameter.name].choices = choices  # type: ignore[attr-defined]


def _build_move_callback(plugin_key: str, move: Any):
    async def _callback(interaction: discord.Interaction, **kwargs: Any) -> None:
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)
        arguments = {"ctx": interaction, **kwargs}
        await handle_move(
            ctx=interaction,
            name=move.name,
            arguments=arguments,
            current_turn_required=move.require_current_turn,
        )

    parameters = [
        inspect.Parameter(
            "interaction",
            kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
            annotation=discord.Interaction,
        )
    ]
    annotations = {"interaction": discord.Interaction}
    for parameter in move.options:
        default = None if parameter.optional else inspect.Parameter.empty
        annotation = _annotation_for_parameter(parameter)
        annotations[parameter.name] = annotation
        parameters.append(
            inspect.Parameter(
                parameter.name,
                kind=inspect.Parameter.KEYWORD_ONLY,
                default=default,
                annotation=annotation,
            )
        )

    _callback.__name__ = f"{plugin_key}_{move.name}"
    _callback.__qualname__ = _callback.__name__
    _callback.__signature__ = inspect.Signature(parameters=parameters)
    _callback.__annotations__ = annotations
    return _callback


def _register_autocomplete(
    command: app_commands.Command[Any, ..., Any],
    move: Any,
) -> None:
    def _make_autocomplete(move_name: str, argument_name: str):
        async def _autocomplete(
            interaction: discord.Interaction,
            current: str,
        ):
            return await handle_autocomplete(
                interaction,
                move_name,
                current,
                argument_name,
            )

        return _autocomplete

    for parameter in move.options:
        if not parameter.autocomplete:
            continue

        command.autocomplete(parameter.name)(
            _make_autocomplete(move.name, parameter.name)
        )


def build_game_group(game: Any) -> app_commands.Group:
    metadata = game.metadata()
    group = app_commands.Group(
        name=game.key,
        description=metadata.move_group_description,
        guild_only=True,
    )
    for move in metadata.moves:
        callback = _build_move_callback(game.key, move)
        command = app_commands.command(
            name=move.name,
            description=move.description,
        )(callback)
        _choices_decorator(command, move)
        _register_autocomplete(command, move)
        group.add_command(command)
    return group


def build_tree(bot: discord.Client) -> list[app_commands.Group]:
    """Return all top-level groups built without `exec`."""

    built_groups = [build_game_group(game) for game in GAMES]
    bot.tree.add_command(command_play)
    for group in built_groups:
        if game := GAME_BY_KEY.get(group.name):
            _ = game
        bot.tree.add_command(group)
    return built_groups
