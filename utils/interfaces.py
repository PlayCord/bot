import asyncio
import importlib
import inspect
import io
import logging
import random
import typing
from typing import Any

import trueskill

from api.Game import PlayerOrder, RoleMode, resolve_player_count
from api.MessageComponents import Container, MediaGallery, Message, TextDisplay, format_data_table_image
from api.Player import Player
from api.Response import Response
from configuration.constants import *
from utils import database as db
from utils.analytics import Timer
from utils.bot_names import generate_bot_name
from utils.containers import (
    CustomContainer,
    ErrorContainer,
    GameOverContainer,
    GameOverviewContainer,
    container_edit_kwargs,
    container_send_kwargs,
    container_to_markdown,
)
from utils.conversion import column_creator, column_elo, column_names, column_turn, contextify, player_representative, \
    player_verification_function, textify
from utils.database import InternalPlayer, get_shallow_player, internal_player_to_player
from utils.emojis import get_emoji_string
from utils.locale import fmt, get
from utils.trueskill_params import get_trueskill_parameters
from utils.views import MatchmakingLobbyView, MatchmakingView, RematchView, SpectateView


def user_in_active_game(user_id: int) -> bool:
    """Return True when the user is currently in any active game across all servers."""
    for player in IN_GAME.keys():
        if getattr(player, "id", None) == user_id:
            return True
    return False


def user_in_active_matchmaking(user_id: int) -> bool:
    """Return True when the user is currently queued in any active matchmaking lobby."""
    for player in IN_MATCHMAKING.keys():
        if getattr(player, "id", None) == user_id:
            return True
    return False


def synthetic_bot_name_from_id(user_id: int) -> str:
    return f"Bot {str(user_id)[-4:]} (Bot)"


class GameInterface:
    """
    A class that handles the interface between the game and discord

    Discord <--> Bot <--> GameInterface <--> Game
    """

    def __init__(self, game_type: str, status_message: discord.InteractionMessage, creator: discord.User,
                 players: list[InternalPlayer | Player], rated: bool, game_id: int,
                 match_options: dict[str, typing.Any] | None = None,
                 match_public_code: str | None = None,
                 role_selections: dict[int, str] | None = None) -> None:
        """
        Create the GameInterface
        :param game_type: The game type as defined in constants.py
        :param status_message: The message already created by the bot outside the not-yet-existent thread
        :param creator: the User (discord) who created the lobby TODO: change to Player
        :param players: A list of Player.py objects representing the players
        :param rated: Whether the game is rated (ratings change based on outcome)
        :param game_id: The match row ID in the database (internal)
        :param match_public_code: Short public code for thread title and replay (defaults to str(game_id))
        """
        # The message created by the bot outside the not-yet-existent thread
        self.game_id = game_id
        self.match_public_code = match_public_code if match_public_code else str(game_id)
        self.status_message = status_message
        self.match_options = dict(match_options) if match_options else {}
        # The game type
        self.game_type = game_type
        self.logger = logging.getLogger(f"GameInterface[{game_type}]")
        # Who created the lobby
        self.creator = creator

        # Get the game class to check player_order setting
        self.module = importlib.import_module(GAME_TYPES[game_type][0])  # Game module
        game_class = getattr(self.module, GAME_TYPES[game_type][1])

        # Order players based on game's player_order setting
        player_order = getattr(game_class, 'player_order', PlayerOrder.RANDOM)

        if player_order == PlayerOrder.RANDOM:
            random.shuffle(players)
        elif player_order == PlayerOrder.PRESERVE:
            pass  # Keep order as-is
        elif player_order == PlayerOrder.CREATOR_FIRST:
            # Move creator to front, shuffle the rest
            creator_player = None
            other_players = []
            for p in players:
                if p.id == creator.id:
                    creator_player = p
                else:
                    other_players.append(p)
            random.shuffle(other_players)
            if creator_player:
                players = [creator_player] + other_players
            else:
                players = other_players
        elif player_order == PlayerOrder.REVERSE:
            players = list(reversed(players))

        players = game_class.seat_players(
            players,
            game_type,
            selections=dict(role_selections) if role_selections else None,
        )

        # All players in the game
        self.players = players
        self.rated = rated  # Is the game rated?
        self.thread = None  # The thread object after self.setup() is called
        self.game_message = None  # The message representing the game after self.setup() is called
        self.info_message = None  # The message showing game info, whose turn, and what players.
        # also made by self.setup()
        # Game class instantiated with the players
        game_players: list[Player] = []
        for participant in players:
            if isinstance(participant, Player):
                game_players.append(participant)
                continue

            if getattr(participant, "is_bot", False):
                game_players.append(
                    Player(
                        mu=MU,
                        sigma=MU * get_trueskill_parameters(self.game_type)["sigma"],
                        ranking=None,
                        id=participant.id,
                        name=getattr(participant, "name", synthetic_bot_name_from_id(participant.id)),
                        is_bot=True,
                        bot_difficulty=getattr(participant, "bot_difficulty", None),
                    )
                )
                continue

            rating = getattr(participant, self.game_type)
            game_players.append(
                Player(
                    mu=rating.mu,
                    sigma=rating.sigma,
                    ranking=None,
                    id=participant.id,
                    name=getattr(participant, "name", None),
                    is_bot=getattr(participant, "is_bot", False),
                    bot_difficulty=getattr(participant, "bot_difficulty", None),
                )
            )

        if "match_options" in inspect.signature(game_class.__init__).parameters:
            self.game = game_class(game_players, match_options=self.match_options)
        else:
            self.game = game_class(game_players)
        self.game.attach_replay_logger(self._replay_sink_from_game)
        _replay_hook = getattr(self.game, "on_replay_logger_attached", None)
        if callable(_replay_hook):
            try:
                _replay_hook()
            except Exception:
                self.logger.getChild("replay").warning(
                    "on_replay_logger_attached failed", exc_info=True
                )

        self.current_turn = None

        for p in players:
            if not getattr(p, "is_bot", False):
                IN_GAME.update({p: self})

        self.processing_move = asyncio.Lock()
        self.processing_bot_turn = False
        self.ending_game = False
        self._pending_ui_tasks: list[asyncio.Task] = []
        self._thread_messages: dict[str, discord.Message] = {}

    def _track_ui_task(self, coro) -> asyncio.Task:
        task = asyncio.create_task(coro)
        self._pending_ui_tasks.append(task)

        def _discard(t: asyncio.Task) -> None:
            try:
                self._pending_ui_tasks.remove(t)
            except ValueError:
                pass

        task.add_done_callback(_discard)
        return task

    async def await_pending_ui_tasks(self, timeout: float = 30.0) -> None:
        pending = [t for t in self._pending_ui_tasks if not t.done()]
        if not pending:
            return
        await asyncio.wait(pending, timeout=timeout)

    async def setup(self) -> None:
        """
        Sets up the game in Discord
        1. Create a private thread off of the channel the bot was called on
        2. Add users to the thread
        3. Send a message to the thread (that is used for the game message)

        Due to an async limitation, this function must be called on the class directly after it is created.
        :return: Nothing
        """
        log = self.logger.getChild("setup")
        setup_timer = Timer().start()
        log.debug(f"Setting up game interface for a new game. matchmaker ID: {self.status_message.id}")
        rated_prefix = get("queue.thread_rated_prefix") if self.rated else ""

        game_thread = await self.status_message.channel.create_thread(  # Create the private thread.
            name=fmt(
                "queue.thread_name",
                prefix=rated_prefix,
                game=self.game.name,
                match_code=self.match_public_code,
            ),
            type=discord.ChannelType.private_thread, invitable=False)  # Don't allow people to add themselves

        for player in self.players:
            if hasattr(player, "user") and player.user is not None:
                try:
                    await game_thread.add_user(player.user)
                except discord.HTTPException as e:
                    log.warning("add_user failed for %s: %s", player.user.id, e)

        loading_message = Message(
            Container(
                TextDisplay(get_emoji_string("loading")),
            )
        )

        # Set the thread and game message in the class
        self.thread = game_thread

        self.info_message = await self.thread.send(**loading_message.to_send_kwargs())
        self.game_message = await self.thread.send(**loading_message.to_send_kwargs())
        log.debug(
            f"Finished game setup for a new game in {setup_timer.stop()}ms."
            f" matchmaker ID: {self.status_message.id} game ID: {self.thread.id}")

    async def move_by_command(self, ctx: discord.Interaction, name: str, arguments: dict[str, typing.Any],
                              current_turn_required: bool = True) -> None:
        """
        Make a move by command. This function is called dynamically by handle_move in the main program.
        Game move handlers must be synchronous (return ``Response`` or ``None``).
        How it works:
        1. Call the game's move function
        2. Update the game message based on the changes to the move
        :param current_turn_required: whether the current turn is required for this command
        :param name: Name of movement function to call
        :param ctx: Discord context window
        :param arguments: the list of preparsed arguments to pass directly into the move function
        :return: None
        """
        log = self.logger.getChild("move[command]")
        if self.ending_game:  # Don't move if the game is ending
            log.warning(f"Denied interaction to command {name!r} with arguments {arguments!r}"
                        f" because the game is ending!"
                        f" context: {contextify(ctx)}")
            return

        async with self.processing_move:  # Get move processing lock
            log.debug(f"Now processing move command {name!r} with arguments {arguments!r} context: {contextify(ctx)}")
            self.current_turn = self.game.current_turn()
            if getattr(self.current_turn, "is_bot", False):
                message = await ctx.followup.send(content=PERMISSION_MSG_NOT_YOUR_TURN, ephemeral=True)
                await message.delete(delay=5)
                return
            if ctx.user.id != self.current_turn.id and current_turn_required:
                log.debug(f"current_turn_required command failed because it isn't this player's turn"
                          f" (should be {self.current_turn}) context: {contextify(ctx)}")
                message = await ctx.followup.send(content=PERMISSION_MSG_NOT_YOUR_TURN, ephemeral=True)
                await message.delete(delay=5)
                return
            function_to_call = self._resolve_move_callable(name)
            try:
                # Call the move function with arguments (player, <expanded arguments>
                move_response: Response = getattr(self.game, function_to_call)(
                    internal_player_to_player(db.database.get_player(ctx.user, ctx.guild.id), self.game_type),
                    **arguments)
            except Exception:
                log.exception(
                    "move_by_command failed name=%r arguments=%r context=%s",
                    name,
                    arguments,
                    contextify(ctx),
                )
                error_embed = ErrorContainer(
                    ctx,
                    what_failed=get("move.unexpected_processing_error"),
                    reason=None,
                )
                await ctx.followup.send(**container_send_kwargs(error_embed), ephemeral=True)
                return

            try:
                if move_response is not None:
                    send_move, set_delete_hook = move_response.generate_message(ctx.followup.send, self.thread.id,
                                                                                enable_view_components=False)
                    sent_message = await send_move
                    if sent_message is False:  # This means there was a null Response, so delete
                        try:
                            await ctx.delete_original_response()
                        except Exception:
                            log.warning(
                                "delete_original_response failed (slash move) name=%r context=%s",
                                name,
                                contextify(ctx),
                                exc_info=True,
                            )
                    hook = set_delete_hook(sent_message)
                    if hook:
                        await hook
                else:
                    try:
                        await ctx.delete_original_response()
                    except Exception:
                        log.warning(
                            "delete_original_response failed (slash move) name=%r context=%s",
                            name,
                            contextify(ctx),
                            exc_info=True,
                        )
            except Exception:
                log.exception(
                    "move_by_command UI phase failed name=%r context=%s",
                    name,
                    contextify(ctx),
                )
                try:
                    await ctx.followup.send(
                        **container_send_kwargs(ErrorContainer(
                            ctx,
                            what_failed=get("move.unexpected_processing_error"),
                            reason=None,
                        )),
                        ephemeral=True,
                    )
                except Exception:
                    pass

            try:
                await self._move_postamble(
                    ctx=ctx,
                    move_response=move_response,
                    python_callback_name=function_to_call,
                    persist_user_id=ctx.user.id,
                    persist_args=dict(arguments),
                    interaction_kind="slash_command",
                )
            except Exception:
                log.exception(
                    "move_by_command postamble failed name=%r context=%s",
                    name,
                    contextify(ctx),
                )
                try:
                    await ctx.followup.send(
                        **container_send_kwargs(ErrorContainer(
                            ctx,
                            what_failed=get("move.unexpected_processing_error"),
                            reason=None,
                        )),
                        ephemeral=True,
                    )
                except Exception:
                    pass

    def _resolve_move_callable(self, command_name: str) -> str:
        callback = None
        for command in self.game.moves:
            if command.name == command_name:
                callback = command.callback
                break
        return command_name if callback is None else callback

    def _replay_sink_from_game(self, event: dict) -> None:
        try:
            if not isinstance(event, dict):
                return
            row = dict(event)
            row.setdefault("type", "game_event")
            db.database.append_replay_event(self.game_id, row)
        except Exception as e:
            self.logger.getChild("replay").warning("append_replay_event failed: %s", e, exc_info=True)

    def _lookup_move_command(self, python_callback_name: str):
        for cmd in self.game.moves:
            effective = cmd.callback if cmd.callback is not None else cmd.name
            if effective == python_callback_name:
                return cmd
        return None

    async def _move_postamble(
            self,
            *,
            ctx: discord.Interaction,
            move_response: Any,
            python_callback_name: str,
            persist_user_id: int,
            persist_args: dict[str, Any],
            interaction_kind: str,
    ) -> None:
        log = self.logger.getChild("move[postamble]")
        await self.display_game_state()
        await self._sync_thread_messages()
        await self._dispatch_private_updates(ctx)
        _cmd = self._lookup_move_command(python_callback_name)
        if self._should_persist_move_replay(move_response, _cmd):
            self._persist_move_and_replay(
                python_callback_name, persist_user_id, persist_args, interaction_kind
            )
        if (outcome := self.game.outcome()) is not None:
            log.debug(
                "Received not-null game outcome: %r context: %s",
                outcome,
                contextify(ctx),
            )
            message = await ctx.followup.send(content=get("game.over_short"), ephemeral=True)
            await message.delete(delay=5)
            await game_over(self, outcome)

    @staticmethod
    def _should_persist_move_replay(move_response: Any, cmd) -> bool:
        """
        Persist replay / match_moves only when a game-affecting callback actually changed state (or opted in).

        Returning ``None`` means success; returning ``Response`` is usually validation/no-op unless
        ``record_replay=True``. Non-affecting commands (e.g. peek) never persist.
        """
        affecting = cmd.is_game_affecting if cmd is not None else True
        if cmd is not None and not affecting:
            return False
        if move_response is None:
            return True
        if isinstance(move_response, Response) and getattr(move_response, "record_replay", False):
            return True
        return False

    @staticmethod
    def _json_safe_for_move(value: Any) -> Any:
        if value is None or isinstance(value, (bool, int, float, str)):
            return value
        if isinstance(value, dict):
            return {str(k): GameInterface._json_safe_for_move(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [GameInterface._json_safe_for_move(v) for v in value]
        if hasattr(value, "id") and hasattr(value, "name"):
            return {
                "id": getattr(value, "id", None),
                "name": str(getattr(value, "name", "")),
                "is_bot": bool(getattr(value, "is_bot", False)),
            }
        return str(value)

    def _persist_move_and_replay(
            self,
            python_callback_name: str,
            user_id: int | None,
            arguments: dict[str, Any],
            source: str,
    ) -> None:
        try:
            cmd = self._lookup_move_command(python_callback_name)
            affecting = cmd.is_game_affecting if cmd else True
            move_no = db.database.get_move_count(self.game_id) + 1
            move_data = {
                "source": source,
                "game_type": self.game_type,
                "python_callback": python_callback_name,
                "command_name": cmd.name if cmd else python_callback_name,
                "arguments": self._json_safe_for_move(dict(arguments)),
            }
            db.database.record_move(
                self.game_id,
                user_id,
                move_no,
                move_data,
                game_state_after=None,
                time_taken_ms=None,
                is_game_affecting=affecting,
            )
            evt = {
                "type": "move",
                "move_number": move_no,
                "command_name": cmd.name if cmd else python_callback_name,
                "python_callback": python_callback_name,
                "user_id": user_id,
                "arguments": move_data["arguments"],
                "is_game_affecting": affecting,
            }
            db.database.append_replay_event(self.game_id, evt)
        except Exception as e:
            self.logger.getChild("replay").warning("persist move failed: %s", e, exc_info=True)

    async def _send_bot_response(self, move_response: Response) -> None:
        async def send_to_thread(**kwargs):
            kwargs.pop("ephemeral", None)
            return await self.thread.send(**kwargs)

        send_move, set_delete_hook = move_response.generate_message(
            send_to_thread,
            self.thread.id,
            enable_view_components=False,
        )
        sent_message = await send_move
        if sent_message is not False:
            hook = set_delete_hook(sent_message)
            if hook:
                await hook

    async def execute_bot_turn(self) -> None:
        log = self.logger.getChild("move[bot]")
        if self.ending_game or self.processing_bot_turn:
            return

        self.processing_bot_turn = True
        replay_python_fn: str | None = None
        replay_args: dict[str, Any] = {}
        try:
            await asyncio.sleep(1.0)
            move_response = None
            async with self.processing_move:
                self.current_turn = self.game.current_turn()
                if not getattr(self.current_turn, "is_bot", False):
                    return

                bot_difficulty = getattr(self.current_turn, "bot_difficulty", None)
                available_bots = getattr(self.game, "bots", {})
                bot_definition = available_bots.get(bot_difficulty)
                if bot_definition is None:
                    await self.thread.send(fmt("game.bot_failed_move", player=self.current_turn.mention))
                    return

                callback_name = bot_definition.callback if bot_definition.callback is not None else bot_difficulty
                callback = getattr(self.game, callback_name, None)
                if callback is None:
                    await self.thread.send(fmt("game.bot_failed_move", player=self.current_turn.mention))
                    return

                await self.display_game_state()

                bot_result = callback(self.current_turn)
                if inspect.isawaitable(bot_result):
                    bot_result = await bot_result

                move_response = None
                if isinstance(bot_result, dict):
                    command_name = bot_result.get("name") or bot_result.get("command")
                    command_arguments = bot_result.get("arguments", {})
                    if command_name is None:
                        await self.thread.send(fmt("game.bot_failed_move", player=self.current_turn.mention))
                        return
                    function_name = self._resolve_move_callable(command_name)
                    replay_python_fn = function_name
                    replay_args = dict(command_arguments)
                    move_response = getattr(self.game, function_name)(self.current_turn, **command_arguments)
                elif isinstance(bot_result, tuple) and len(bot_result) == 2:
                    command_name, command_arguments = bot_result
                    function_name = self._resolve_move_callable(command_name)
                    replay_python_fn = function_name
                    replay_args = dict(command_arguments)
                    move_response = getattr(self.game, function_name)(self.current_turn, **command_arguments)
                elif isinstance(bot_result, str):
                    function_name = self._resolve_move_callable(bot_result)
                    replay_python_fn = function_name
                    replay_args = {}
                    move_response = getattr(self.game, function_name)(self.current_turn)
                else:
                    move_response = bot_result

            if inspect.isawaitable(move_response):
                move_response = await move_response

            if isinstance(move_response, Response):
                await self._send_bot_response(move_response)

            await self.display_game_state()

            if replay_python_fn is not None:
                uid = getattr(self.current_turn, "id", None)
                _bcmd = self._lookup_move_command(replay_python_fn)
                if self._should_persist_move_replay(move_response, _bcmd):
                    self._persist_move_and_replay(replay_python_fn, uid, replay_args, "bot")

            if (outcome := self.game.outcome()) is not None:
                await game_over(self, outcome)
                return
        except Exception as err:
            log.error(f"Bot turn failed with error {err!r}", exc_info=True)
            if self.thread is not None:
                try:
                    await self.thread.send(
                        **container_send_kwargs(ErrorContainer(
                            ctx=None,
                            what_failed=get("move.unexpected_processing_error"),
                            reason=None,
                        ))
                    )
                except Exception:
                    await self.thread.send(
                        fmt("game.bot_failed_move", player=getattr(self.current_turn, "mention", "Bot"))
                    )
        finally:
            self.processing_bot_turn = False

    async def move_by_button(self, ctx: discord.Interaction, name, arguments: dict[str, typing.Any],
                             current_turn_required: bool = True) -> None:
        """
        Callback for a move triggered by a button. This function is called dynamically by
        game_button_callback in the main program.
        Game move handlers must be synchronous (return ``Response`` or ``None``); async move callbacks are not supported.
        :param ctx: discord Context for button interaction
        :param name: Name of game function to callback
        :param arguments: arguments to pass directly into the button function
        :param current_turn_required: whether the current turn is required for the button click
        :return: Nothing
        """
        log = self.logger.getChild("move[button]")
        if self.ending_game:  # Don't move if the game is ending
            log.warning(f"Denied interaction to command {name!r} with arguments {arguments!r}"
                        f" because the game is ending!"
                        f" context: {contextify(ctx)}")
            return

        async with self.processing_move:  # Get move processing lock
            log.debug(f"Now processing move command {name!r} with arguments {arguments!r} context: {contextify(ctx)}")
            # Update current turn
            self.current_turn = self.game.current_turn()

            # Check to make sure that it is current turn (if required)
            if getattr(self.current_turn, "is_bot", False):
                message = await ctx.followup.send(content=PERMISSION_MSG_NOT_YOUR_TURN, ephemeral=True)
                await message.delete(delay=5)
                return
            if ctx.user.id != self.current_turn.id and current_turn_required:
                log.debug(f"current_turn_required command failed because it isn't this player's turn"
                          f" (should be {self.current_turn.id} ({self.current_turn.name})) context: {contextify(ctx)}")
                message = await ctx.followup.send(content=PERMISSION_MSG_NOT_YOUR_TURN, ephemeral=True)
                await message.delete(delay=5)
                return

            # Get callback
            callback_function = getattr(self.game, name)

            # Get signature
            signature = inspect.signature(callback_function).parameters

            # Convert str to int and float if required
            type_converted_arguments = {}
            for arg in arguments:
                argument_type = signature[arg].annotation
                if argument_type is int:
                    type_converted_arguments[arg] = int(arguments[arg])
                elif argument_type is float:
                    type_converted_arguments[arg] = float(arguments[arg])
                else:
                    type_converted_arguments[arg] = arguments[arg]

            # Call button's callback with player and converted arguments
            try:
                # Call the move function with arguments (player, <expanded arguments>)
                move_response: Response = callback_function(
                    internal_player_to_player(db.database.get_player(ctx.user, ctx.guild.id), self.game_type),
                    **type_converted_arguments)
            except Exception:
                log.exception(
                    "move_by_button failed name=%r arguments=%r context=%s",
                    name,
                    arguments,
                    contextify(ctx),
                )
                error_embed = ErrorContainer(
                    ctx,
                    what_failed=get("move.unexpected_processing_error"),
                    reason=None,
                )
                await ctx.followup.send(**container_send_kwargs(error_embed), ephemeral=True)
                return

            try:
                if move_response is not None:
                    send_move, set_delete_hook = move_response.generate_message(ctx.followup.send, self.thread.id,
                                                                                enable_view_components=False)
                    sent_message = await send_move
                    hook = set_delete_hook(sent_message)
                    if hook:
                        await hook
            except Exception:
                log.exception(
                    "move_by_button UI phase failed name=%r context=%s",
                    name,
                    contextify(ctx),
                )
                try:
                    await ctx.followup.send(
                        **container_send_kwargs(ErrorContainer(
                            ctx,
                            what_failed=get("move.unexpected_processing_error"),
                            reason=None,
                        )),
                        ephemeral=True,
                    )
                except Exception:
                    pass

            try:
                await self._move_postamble(
                    ctx=ctx,
                    move_response=move_response,
                    python_callback_name=name,
                    persist_user_id=ctx.user.id,
                    persist_args=dict(type_converted_arguments),
                    interaction_kind="button",
                )
            except Exception:
                log.exception(
                    "move_by_button postamble failed name=%r context=%s",
                    name,
                    contextify(ctx),
                )
                try:
                    await ctx.followup.send(
                        **container_send_kwargs(ErrorContainer(
                            ctx,
                            what_failed=get("move.unexpected_processing_error"),
                            reason=None,
                        )),
                        ephemeral=True,
                    )
                except Exception:
                    pass

    async def move_by_select(self, ctx: discord.Interaction, name: str, current_turn_required: bool = True):
        """
        Select-menu moves: the game's callback receives ``(player, ctx.data['values'])``.
        Handlers must be synchronous like ``move_by_button``.
        """
        log = self.logger.getChild("move[select]")
        if self.ending_game:  # Don't move if the game is ending
            log.warning(f"Denied interaction to command {name!r}"
                        f" because the game is ending!"
                        f" context: {contextify(ctx)}")
            return

        async with self.processing_move:  # Get move processing lock
            log.debug(f"Now processing move command {name!r} context: {contextify(ctx)}")
            # Update current turn
            self.current_turn = self.game.current_turn()

            # Check to make sure that it is current turn (if required)
            if getattr(self.current_turn, "is_bot", False):
                message = await ctx.followup.send(content=PERMISSION_MSG_NOT_YOUR_TURN, ephemeral=True)
                await message.delete(delay=5)
                return
            if ctx.user.id != self.current_turn.id and current_turn_required:
                log.debug(f"current_turn_required command failed because it isn't this player's turn"
                          f" (should be {self.current_turn.id} ({self.current_turn.name})) context: {contextify(ctx)}")
                message = await ctx.followup.send(content=PERMISSION_MSG_NOT_YOUR_TURN, ephemeral=True)
                await message.delete(delay=5)
                return

            # Get callback
            callback_function = getattr(self.game, name)

            # Call button's callback with player and converted arguments
            try:
                # Call the move function with arguments (player, values)
                move_response: Response = callback_function(
                    internal_player_to_player(db.database.get_player(ctx.user, ctx.guild.id), self.game_type),
                    ctx.data["values"])
            except Exception:
                log.exception(
                    "move_by_select failed name=%r context=%s",
                    name,
                    contextify(ctx),
                )
                error_embed = ErrorContainer(
                    ctx,
                    what_failed=get("move.unexpected_processing_error"),
                    reason=None,
                )
                await ctx.followup.send(**container_send_kwargs(error_embed), ephemeral=True)
                return

            try:
                if move_response is not None:
                    send_move, set_delete_hook = move_response.generate_message(ctx.followup.send, self.thread.id,
                                                                                enable_view_components=False)
                    sent_message = await send_move
                    hook = set_delete_hook(sent_message)
                    if hook:
                        await hook
            except Exception:
                log.exception(
                    "move_by_select UI phase failed name=%r context=%s",
                    name,
                    contextify(ctx),
                )
                try:
                    await ctx.followup.send(
                        **container_send_kwargs(ErrorContainer(
                            ctx,
                            what_failed=get("move.unexpected_processing_error"),
                            reason=None,
                        )),
                        ephemeral=True,
                    )
                except Exception:
                    pass

            try:
                await self._move_postamble(
                    ctx=ctx,
                    move_response=move_response,
                    python_callback_name=name,
                    persist_user_id=ctx.user.id,
                    persist_args={"values": ctx.data.get("values", [])},
                    interaction_kind="select",
                )
            except Exception:
                log.exception(
                    "move_by_select postamble failed name=%r context=%s",
                    name,
                    contextify(ctx),
                )
                try:
                    await ctx.followup.send(
                        **container_send_kwargs(ErrorContainer(
                            ctx,
                            what_failed=get("move.unexpected_processing_error"),
                            reason=None,
                        )),
                        ephemeral=True,
                    )
                except Exception:
                    pass

    def _build_info_message(self, turn_description: str) -> Message:
        info_table = format_data_table_image(
            {
                player: {
                    "Rating": rating,
                    "Turn": turn_marker,
                }
                for player, rating, turn_marker in zip(
                self.players,
                column_elo(self.players, self.game_type).split("\n"),
                column_turn(self.players, self.current_turn).split("\n"),
                strict=False,
            )
            }
        )
        return Message(
            Container(
                TextDisplay(f"## {fmt('game.state_title', game=self.game.name, players=len(self.players))}"),
                TextDisplay(turn_description),
                MediaGallery(info_table),
            )
        )

    def _build_status_view(self):
        overview = GameOverviewContainer(self.game.name, self.game_type, self.rated, self.players, self.current_turn)
        return SpectateView(
            spectate_button_id=f"spectate/{self.thread.id}",
            peek_button_id=f"peek/{self.thread.id}/{self.game_message.id}",
            game_link=self.info_message.jump_url if self.info_message is not None else None,
            summary_text=container_to_markdown(overview),
        )

    async def _sync_thread_messages(self) -> None:
        desired = {item.key: item.content for item in (self.game.thread_messages() or [])}

        for key in list(self._thread_messages):
            if key not in desired:
                try:
                    await self._thread_messages[key].delete()
                except discord.HTTPException:
                    pass
                self._thread_messages.pop(key, None)

        for key, message in desired.items():
            if key in self._thread_messages:
                await self._thread_messages[key].edit(**message.to_edit_kwargs(self.thread.id))
            else:
                self._thread_messages[key] = await self.thread.send(**message.to_send_kwargs(self.thread.id))

    async def _dispatch_private_updates(self, ctx: discord.Interaction) -> None:
        actor = db.database.get_player(ctx.user, ctx.guild.id) if ctx.guild is not None else None
        if actor is not None:
            private_message = self.game.player_state(internal_player_to_player(actor, self.game_type))
            if private_message is not None:
                await ctx.followup.send(**private_message.to_send_kwargs(self.thread.id), ephemeral=True)

        if getattr(self.game, "notify_on_turn", False):
            turn_player = self.game.current_turn()
            if getattr(turn_player, "id", None) == getattr(ctx.user, "id", None):
                await ctx.followup.send(self.game.turn_notification(turn_player), ephemeral=True)

    async def display_game_state(self) -> None:
        """
        Use the Game class (self.game) to get an updated version of the game state.
        :return: None
        """
        log = self.logger.getChild("display_game_state")
        update_timer = Timer().start()
        self.current_turn = self.game.current_turn()
        if getattr(self.current_turn, "is_bot", False):
            turn_description = fmt("game.bot_turn_computing", player=self.current_turn.mention)
        else:
            turn_description = textify(TEXTIFY_CURRENT_GAME_TURN, {"player": self.current_turn.mention})
        info_message = self._build_info_message(turn_description)
        game_state = self.game.state()
        if game_state is None:
            game_state = Message(
                Container(
                    TextDisplay(f"**{get('game.empty_state_name')}**"),
                    TextDisplay(get("game.empty_state_value")),
                    accent_color=INFO_COLOR,
                )
            )

        # Edit the game and info messages with the new embeds
        async def edit_info_message():
            while self.info_message is None:
                await asyncio.sleep(1)
            await self.info_message.edit(**info_message.to_edit_kwargs())

        self._track_ui_task(edit_info_message())

        async def edit_game_message():
            while self.game_message is None:
                await asyncio.sleep(1)
            await self.game_message.edit(**game_state.to_edit_kwargs(self.thread.id))

        self._track_ui_task(edit_game_message())

        # Edit overview embed with new data
        async def edit_status_message():
            while self.status_message is None:
                await asyncio.sleep(1)
            await self.status_message.edit(view=self._build_status_view())

        self._track_ui_task(edit_status_message())

        # async def purge_phantom():
        #     while self.game_message is None:
        #         await asyncio.sleep(1)
        #     await self.game_message.channel.purge(limit=100, check=lambda msg: not (msg.guild.me == msg.author))
        #
        # asyncio.create_task(purge_phantom())

        log.debug(f"Finished game state update task in {update_timer.stop()}ms."
                  f" game_id={self.thread.id} game_type={self.game_type}")

        if getattr(self.current_turn, "is_bot", False) and not self.ending_game and not self.processing_bot_turn:
            asyncio.create_task(self.execute_bot_turn())

    async def bump(self):
        self.game_message = await self.game_message.channel.send()


class MatchmakingInterface:
    """
    MatchmakingInterface - the class that handles matchmaking for a game, where control is promptly handed off to a GameInterface
    via the successful_matchmaking function.
    """

    def __init__(self, creator: discord.User, game_type: str, message: discord.InteractionMessage,
                 rated: bool, private: bool):

        # Whether the startup of the matchmaking interaction failed
        self.failed = None

        # Game type
        self.game_type = game_type

        # Creator of the game
        self.creator = creator

        # Is the game rated?
        self.rated = rated

        # Whether joining the game is open
        self.private = private

        # Allowed players for whitelist
        self.whitelist = {db.database.get_player(creator, message.guild.id)}

        # Disallowed players (blacklist
        self.blacklist = set()

        # Game module
        self.module = importlib.import_module(GAME_TYPES[game_type][0])

        # Start the list of queued players with just the creator
        self.queued_players = set(self.whitelist)
        self.bots: list[Player] = []

        # The message context to edit when making updates
        self.message = message

        if self.queued_players == {None}:  # Couldn't get information on the creator, so fail now
            self.failed = ErrorContainer(
                what_failed=get("queue.db_connect_failed_what"),
                reason=get("queue.db_connect_failed_reason"),
            )
            return
        CURRENT_MATCHMAKING.update({self.message.id: self})
        IN_MATCHMAKING.update({p: self for p in self.queued_players})

        # Game class
        self.game = getattr(self.module, GAME_TYPES[game_type][1])

        self.rated_requested = self.rated
        self._specs = tuple(getattr(self.game, "customizable_options", ()) or ())
        self.match_settings: dict[str, str | int] = {s.key: s.default for s in self._specs}
        self.role_selections: dict[int, str] = {}
        self._sync_rated_flag()

        # Required and maximum players for game TODO: more complex requirements for start/stop

        player_count = resolve_player_count(self.game)
        if player_count is None:  # If no player count is defined, any value is "fine"
            self.player_verification_function = lambda x: True
            self.allowed_players = get("queue.any_players")
        else:
            self.player_verification_function = player_verification_function(player_count)
            self.allowed_players = player_representative(player_count)

        self.outcome = None  # Whether the matchmaking was successful (True, None, or False)
        self.logger = logging.getLogger(f"playcord.matchmaking_interface[{message.id}]")

    @property
    def has_bots(self) -> bool:
        return len(self.bots) > 0

    def _match_settings_are_default(self) -> bool:
        for spec in self._specs:
            if self.match_settings.get(spec.key, spec.default) != spec.default:
                return False
        return True

    def _sync_rated_flag(self) -> None:
        if self.has_bots:
            self.rated = False
            return
        if (
                self._specs
                and getattr(self.game, "customization_forces_unrated_when_non_default", True)
                and not self._match_settings_are_default()
        ):
            self.rated = False
            return
        self.rated = self.rated_requested

    def all_players(self) -> list[InternalPlayer | Player]:
        return [*sorted(self.queued_players, key=lambda p: p.id), *self.bots]

    def add_bot(self, difficulty: str) -> str | None:
        available_bots = getattr(self.game, "bots", {})
        if not available_bots:
            return get("queue.bot_not_supported")
        if difficulty not in available_bots:
            return fmt("queue.bot_invalid_difficulty", difficulty=difficulty)
        if any(bot.bot_difficulty == difficulty for bot in self.bots):
            return fmt("queue.bot_already_added", difficulty=difficulty)

        current_count = len(self.queued_players) + len(self.bots)
        player_count = resolve_player_count(self.game)
        if isinstance(player_count, list):
            if (current_count + 1) not in player_count:
                return get("queue.bot_too_many_for_game")
        elif isinstance(player_count, int) and (current_count + 1) != player_count:
            return get("queue.bot_too_many_for_game")

        used_names = {getattr(p, "name", None) for p in self.bots if getattr(p, "name", None)}
        bot_name = generate_bot_name(used_names)
        bot_player = Player.create_bot(
            name=bot_name,
            difficulty=difficulty,
            bot_index=len(self.bots),
        )
        self.bots.append(bot_player)
        self._sync_rated_flag()
        return None

    async def callback_lobby_option(self, ctx: discord.Interaction, key: str) -> None:
        """Handle string select for a lobby :attr:`customizable_options` key (creator only)."""
        log = self.logger.getChild("lobby_option")
        if ctx.user.id != self.creator.id:
            await ctx.followup.send(get("queue.only_creator_lobby_options"), ephemeral=True)
            return
        spec = next((s for s in self._specs if s.key == key), None)
        if spec is None:
            log.warning("unknown lobby option key=%r lobby=%s", key, self.message.id)
            await ctx.followup.send(get("matchmaking.invalid_interaction"), ephemeral=True)
            return
        raw = (ctx.data.get("values") or [""])[0]
        self.match_settings[key] = spec.coerce(raw)
        preset_values = spec.applied_preset(raw)
        if preset_values:
            for other_spec in self._specs:
                if other_spec.key in preset_values:
                    self.match_settings[other_spec.key] = other_spec.coerce(str(preset_values[other_spec.key]))
        self._sync_rated_flag()
        await self.update_embed()
        await ctx.followup.send(get("queue.lobby_option_updated"), ephemeral=True)

    async def callback_role_select(self, ctx: discord.Interaction, player_id: int) -> None:
        """Handle per-player role string select for CHOSEN :attr:`role_mode`."""
        log = self.logger.getChild("lobby_role_select")
        if ctx.user.id != player_id:
            await ctx.followup.send(get("queue.role_select_not_yours"), ephemeral=True)
            return
        if getattr(self.game, "role_mode", RoleMode.NONE) != RoleMode.CHOSEN:
            log.warning("role select on non-CHOSEN lobby lobby=%s", self.message.id)
            await ctx.followup.send(get("matchmaking.invalid_interaction"), ephemeral=True)
            return
        raw = (ctx.data.get("values") or [""])[0]
        self.role_selections[player_id] = str(raw)
        await self.update_embed()
        await ctx.followup.send(get("queue.role_select_updated"), ephemeral=True)

    async def update_embed(self) -> None:
        """
        Update the embed based on the players in self.players
        :return: Nothing
        """
        log = self.logger.getChild("update_embed")
        update_timer = Timer().start()
        # Set up the embed

        game_rated_text = get("queue.rated") if self.rated else get("queue.not_rated")
        private_text = get("queue.private_status") if self.private else get("queue.public_status")

        desc_suffix = ""
        if (
                self._specs
                and self.rated_requested
                and not self.rated
                and not self.has_bots
                and not self._match_settings_are_default()
                and getattr(self.game, "customization_forces_unrated_when_non_default", True)
        ):
            desc_suffix = f"\n\n{get('queue.customization_unrated_note')}"

        # Parameters in embed title:
        # Time
        # Allowed players
        # Difficulty
        # Rated/Unrated
        # Public/Private

        game_metadata = {}

        for param in ["time", "difficulty", "author", "author_link", "source_link"]:
            if hasattr(self.game, param):
                game_metadata[param] = getattr(self.game, param)
            else:
                game_metadata[param] = get("help.game_info.unknown")

        container = CustomContainer(
            title=fmt("queue.title", game=self.game.name),
            description=(
                f"⏰{game_metadata['time']}{LONG_SPACE_EMBED * 2}"
                f"👤{self.allowed_players}{LONG_SPACE_EMBED * 2}"
                f"📈{game_metadata['difficulty']}{LONG_SPACE_EMBED * 2}"
                f"📊{game_rated_text}{LONG_SPACE_EMBED * 2}"
                f"{private_text}{desc_suffix}"
            ),
        )

        all_players = self.all_players()
        matchmaking_table = format_data_table_image(
            {
                player: {
                    get("queue.field_rating"): rating,
                    get("queue.field_creator"): creator_marker,
                }
                for player, rating, creator_marker in zip(
                all_players,
                column_elo(all_players, self.game_type).split("\n"),
                column_creator(all_players, self.creator).split("\n"),
                strict=False,
            )
            }
        )
        table_file = discord.File(io.BytesIO(matchmaking_table), filename="matchmaking_table.png")
        table_image_url = f"attachment://{table_file.filename}"

        # Add whitelist or blacklist depending on private status
        if self.private:
            container.add_field(name=get("queue.field_whitelist"), value=column_names(self.whitelist), inline=True)
        elif len(self.blacklist):
            container.add_field(name=get("queue.field_blacklist"), value=column_names(self.blacklist), inline=True)

        try:
            container.set_footer(text=self.game.description)
        except Exception:
            # Fallback: if footer cannot be set for some reason, add as normal fields
            if self.game.description:
                container.add_field(name=get("queue.field_game_info"), value=self.game.description, inline=False)
            if author:
                container.add_field(name=get("queue.field_game_by"), value=str(author), inline=False)

        if self._specs:
            opt_lines = []
            for spec in self._specs:
                v = self.match_settings.get(spec.key, spec.default)
                opt_lines.append(f"**{spec.label}** → `{v}`")
            container.add_field(
                name=get("queue.field_match_options"),
                value="\n".join(opt_lines),
                inline=False,
            )

        role_mode = getattr(self.game, "role_mode", RoleMode.NONE)
        pr_roles = getattr(self.game, "player_roles", None)
        layout_ok_chosen = len(self._specs) + len(self.all_players()) <= 4
        show_role_selects = (
                role_mode == RoleMode.CHOSEN
                and not self.has_bots
                and pr_roles is not None
                and len(pr_roles) == len(self.all_players())
                and layout_ok_chosen
        )
        if role_mode == RoleMode.CHOSEN:
            if self.has_bots:
                container.add_field(
                    name=get("queue.role_picks_field"),
                    value=get("queue.role_chosen_no_bots"),
                    inline=False,
                )
            elif pr_roles and len(pr_roles) == len(self.all_players()):
                if not layout_ok_chosen:
                    container.add_field(
                        name=get("queue.role_picks_field"),
                        value=get("queue.role_chosen_ui_overflow"),
                        inline=False,
                    )
                else:
                    pick_lines = []
                    for p in sorted(self.queued_players, key=lambda x: x.id):
                        picked = self.role_selections.get(p.id)
                        label = getattr(p, "name", None) or str(p.id)
                        if picked:
                            pick_lines.append(f"**{label}** → `{picked}`")
                        else:
                            pick_lines.append(f"**{label}** → {get('queue.role_picks_none')}")
                    container.add_field(
                        name=get("queue.role_picks_field"),
                        value="\n".join(pick_lines) if pick_lines else get("queue.role_picks_none"),
                        inline=False,
                    )
            elif pr_roles:
                container.add_field(
                    name=get("queue.role_picks_field"),
                    value=get("queue.role_chosen_lobby_not_full"),
                    inline=False,
                )

        # Can the start button be pressed?
        start_enabled = self.player_verification_function(len(self.queued_players))
        player_count = resolve_player_count(self.game)
        if isinstance(player_count, list):
            start_enabled = len(self.all_players()) in player_count
        elif isinstance(player_count, int):
            start_enabled = len(self.all_players()) == player_count

        # Create matchmaking button view (with callbacks and can_start)
        join_id = f"join/{self.message.id}"
        leave_id = f"leave/{self.message.id}"
        start_id = f"start/{self.message.id}"
        role_specs_list: list[tuple[int, str, tuple[str, ...]]] = []
        if show_role_selects and pr_roles is not None:
            avail = tuple(pr_roles)
            for p in sorted(self.queued_players, key=lambda x: x.id):
                disp = getattr(p, "name", None) or str(p.id)
                role_specs_list.append((p.id, disp, avail))
        use_lobby_view = bool(self._specs) or show_role_selects
        if use_lobby_view:
            view = MatchmakingLobbyView(
                join_button_id=join_id,
                leave_button_id=leave_id,
                start_button_id=start_id,
                can_start=start_enabled,
                lobby_message_id=self.message.id,
                option_specs=self._specs,
                current_values=dict(self.match_settings),
                role_specs=role_specs_list,
                current_role_values=dict(self.role_selections),
                summary_text=container_to_markdown(container),
                table_image_url=table_image_url,
            )
        else:
            view = MatchmakingView(
                join_button_id=join_id,
                leave_button_id=leave_id,
                start_button_id=start_id,
                can_start=start_enabled,
                summary_text=container_to_markdown(container),
                table_image_url=table_image_url,
            )

        await self.message.edit(view=view, attachments=[table_file])
        log.debug(f"Finished matchmaking update task in {update_timer.stop()}ms.")

    async def seed_rematch_players(self, guild: discord.Guild, user_ids: list[int]) -> str | None:
        """Add humans from a finished match to this lobby (creator is already queued)."""
        present = {p.id for p in self.queued_players}
        for uid in user_ids:
            if uid in present:
                continue
            try:
                member = await guild.fetch_member(uid)
            except (discord.NotFound, discord.HTTPException):
                return fmt("rematch.member_missing", mention=f"<@{uid}>")
            player = db.database.get_player(member, guild.id)
            if player is None:
                return get("rematch.db_failed")
            self.queued_players.add(player)
            IN_MATCHMAKING[player] = self
        return None

    async def accept_invite(self, ctx: discord.Interaction) -> bool:
        """
        Accept a invite.
        :param ctx: discord context with information about the invite
        :return: whether the invite succeeded or failed
        """

        player = get_shallow_player(ctx.user)

        # Get logger
        log = self.logger.getChild("accept_invite")
        log.debug(f"Attempting to accept invite for player {player} for matchmaker id={self.message.id}"
                  f" {contextify(ctx)}")

        if player.id in [p.id for p in self.queued_players]:  # Can't join if you are already in
            log.debug(
                f"Player.py {player} attempted to accept invite, but they are already in the game! "
                f"{contextify(ctx)}")
            await ctx.followup.send(get("queue.already_in_game"), ephemeral=True)
            return False
        if user_in_active_game(player.id):
            log.info(f"Player.py {player} attempted to accept invite while already in another active game."
                     f" {contextify(ctx)}")
            await ctx.followup.send(
                get("queue.already_in_active_game_other_server"),
                ephemeral=True
            )
            return False
        if user_in_active_matchmaking(player.id):
            log.info(
                f"Player.py {player} attempted to accept invite while already queued in another lobby."
                f" {contextify(ctx)}"
            )
            await ctx.followup.send(
                get("queue.already_in_another_queue"),
                ephemeral=True,
            )
            return False
        else:
            if player is None:  # Couldn't retrieve information, so don't join them
                log.warning(
                    f"Player.py {player} attempted to accept invite, but we couldn't connect to the database!"
                    f"{contextify(ctx)}")
                await ctx.followup.send(get("queue.couldnt_connect_db"), ephemeral=True)
                return False

            # Add to whitelist or remove from blacklist, depending on private/public status
            if self.private:
                self.whitelist.add(player)
            else:
                try:
                    self.blacklist.remove(player)
                except KeyError:
                    pass

            self.queued_players.add(player)  # Add the player to queued_players
            IN_MATCHMAKING.update({player: self})
            log.debug(
                f"Successfully accepted invite for {player.id} ({player.name})!"
                f"{contextify(ctx)}")
            await self.update_embed()  # Update embed on discord side
        return True

    async def ban(self, player: discord.User, reason: str) -> str | None:
        """
        Ban a player from the game with reason
        :param player: the player to ban
        :param reason: the reason the player was banned
        :return: Error code or None if no error
        """
        log = self.logger.getChild("ban")
        new_player = db.database.get_player(player, self.message.guild.id)
        log.debug(f"Attempting to ban player {new_player} for reason {reason!r}...")
        if new_player is None:  # Couldn't retrieve information, so don't join them
            log.error(f"Error banning {new_player}: couldn't connect to the database!")
            return get("queue.couldnt_connect_db")

        # Kick if already in and update embed
        kicked = False
        if new_player.id in [p.id for p in self.queued_players]:
            kicked = True
            self.queued_players.remove(new_player)
            IN_MATCHMAKING.pop(new_player)
            self.role_selections.pop(new_player.id, None)

        # end game if necessary
        if not len(self.queued_players):
            await self.message.delete()  # Remove matchmaking message
            self.outcome = False
            log.info(f"Self ban of player {new_player} caused the lobby to end.")
            return get("queue.self_ban_only_player")

        if player.id == self.creator.id:  # Update creator if the person leaving was the creator.
            self.creator = next(iter(self.queued_players)).user

        # If private game: remove from whitelist
        # If public game: add to blacklist
        if self.private:
            try:
                self.whitelist.remove(new_player)
            except KeyError:
                log.info(f"Ban of player {new_player} in private lobby failed: not on whitelist anyway.")
                return get("queue.cant_ban_not_whitelisted")
        else:
            self.blacklist.add(new_player)

        await self.update_embed()  # Update embed now that we have done all operations

        if kicked:
            log.info(f"Successfully kicked and banned {new_player}"
                     f" from the game for reason {reason!r}")
            return fmt("queue.kicked_and_banned", player=player.mention, reason=reason)
        log.info(f"Successfully banned {new_player}"
                 f" from the game for reason {reason!r}")
        return fmt("queue.banned", player=player.mention, reason=reason)

    async def kick(self, player: discord.User, reason: str) -> str | None:
        """
        Kick a player from the game with reason
        :param player: the player to kick
        :param reason: reason the player was kicked
        :return: error or None if no error
        """
        log = self.logger.getChild("kick")
        new_player = get_shallow_player(player)
        log.debug(f"Attempting to kick player {new_player} for reason {reason!r}...")
        if new_player is None:  # Couldn't retrieve information, so don't join them
            log.error(f"Error kicking {new_player}: couldn't connect to the database!")
            return get("queue.couldnt_connect_db")

        kicked = False
        if new_player.id in [p.id for p in self.queued_players]:  # Kick if already in
            kicked = True
            self.queued_players.remove(new_player)
            IN_MATCHMAKING.pop(new_player)
            self.role_selections.pop(new_player.id, None)
            await self.update_embed()

        # end game if necessary
        if not len(self.queued_players):
            await self.message.delete()  # Remove matchmaking message
            self.outcome = False
            log.info(f"Self kick of player {new_player} caused the lobby to end.")
            return get("queue.self_kick_only_player")

        if player.id == self.creator.id:  # Update creator if the person leaving was the creator.
            self.creator = next(iter(self.queued_players)).user

        if kicked:
            log.info(f"Successfully kicked {new_player} ({player.name})"
                     f" from the game for reason {reason!r}")
            return fmt("queue.kicked", player=player.mention, reason=reason)
        log.info(f"Couldn't kick {new_player}"
                 f" from the game: they weren't in the lobby!")
        return fmt("queue.didnt_kick", player=player.mention)

    async def callback_ready_game(self, ctx: discord.Interaction) -> None:
        """
        Callback for the selected player to join the game
        :param ctx: discord context
        :return: Nothing
        """
        log = self.logger.getChild("ready_game")
        new_player = get_shallow_player(ctx.user)
        log.debug(f"Attempting to join the game... {contextify(ctx)}")
        if ctx.user.id in [p.id for p in self.queued_players]:  # Can't join if you are already in
            log.info(f"Attempted to join player {new_player} but failed because they were already in the queue."
                     f" {contextify(ctx)}")
            await ctx.followup.send(get("queue.already_in_game"), ephemeral=True)
        elif user_in_active_game(new_player.id):
            log.info(f"Attempted to join player {new_player} but failed because they are already in another game."
                     f" {contextify(ctx)}")
            await ctx.followup.send(
                get("queue.already_in_active_game_other_server"),
                ephemeral=True
            )
            return
        elif user_in_active_matchmaking(new_player.id):
            log.info(
                f"Attempted to join player {new_player} but failed because they are already queued elsewhere."
                f" {contextify(ctx)}"
            )
            await ctx.followup.send(get("queue.already_in_another_queue"), ephemeral=True)
            return
        else:
            if not self.private:
                if new_player in self.blacklist:
                    log.info(f"Attempted to join player {new_player} but failed because they were already in the queue."
                             f" {contextify(ctx)}")
                    await ctx.followup.send(
                        fmt("queue.banned_message", creator=self.creator.mention),
                        ephemeral=True
                    )
                    return
                self.queued_players.add(new_player)  # Add the player to queued_players
                IN_MATCHMAKING.update({new_player: self})
                await self.update_embed()  # Update embed on discord side
            else:
                if new_player not in self.whitelist:
                    log.info(f"Attempted to join player {new_player} to private game but failed because"
                             f" they were not on the whitelist."
                             f" {contextify(ctx)}")
                    await ctx.followup.send(get("queue.not_on_whitelist"), ephemeral=True)
                    return
                self.queued_players.add(new_player)  # Add the player to queued_players
                IN_MATCHMAKING.update({new_player: self})
                await self.update_embed()  # Update embed on discord side

    async def callback_leave_game(self, ctx: discord.Interaction) -> None:
        """
        Callback for the selected player to leave the matchmaking session
        :param ctx: discord context
        :return: None
        """
        log = self.logger.getChild("leave_game")
        log.debug(f"Attempting to leave the game... {contextify(ctx)}")
        player = get_shallow_player(ctx.user)

        if player.id not in [p.id for p in self.queued_players]:  # Can't leave if you weren't even there
            log.info(f"Attempted to remove player {player} but failed because they weren't in the queue to begin with."
                     f" {contextify(ctx)}")
            await ctx.followup.send(get("queue.not_in_game"), ephemeral=True)
        else:
            # Remove player from queue
            for p in self.queued_players:
                if p.id == player.id:
                    self.queued_players.remove(player)
                    IN_MATCHMAKING.pop(player)
                    self.role_selections.pop(player.id, None)
                    break
            # Nobody is left lol
            if not len(self.queued_players):
                log.info(f"Call to leave_game left no players in lobby, so ending game. {contextify(ctx)}")
                await ctx.followup.send(get("queue.game_cancelled_last_player"),
                                        ephemeral=True)
                await self.message.delete()  # Remove matchmaking message
                self.outcome = False
                return

            if player.id == self.creator.id:  # Update creator if the person leaving was the creator.
                new_creator = next(iter(self.queued_players))
                self.creator = new_creator.user
                log.debug(f"Successful leave_game call did not end the game,"
                          f" but we are removing the creator {player} from the game."
                          f" Selecting new creator {new_creator}. {contextify(ctx)}")

            await self.update_embed()  # Update embed again
        return

    async def callback_start_game(self, ctx: discord.Interaction) -> None:
        """
        Callback for the selected player to start the game.
        :param ctx: Discord context
        :return: Nothing
        """
        log = self.logger.getChild("start_game")
        player = get_shallow_player(ctx.user)
        log.debug(f"Attempting to start the game... {contextify(ctx)}")

        if ctx.user.id != self.creator.id:  # Don't have permissions to start the game
            await ctx.followup.send(get("permissions.cant_start_not_creator"), ephemeral=True)
            log.debug(f"Game failed to start because player {player} was not the creator. "
                      f"{contextify(ctx)}")
            return

        busy_players = [queued_player for queued_player in self.queued_players if user_in_active_game(queued_player.id)]
        if busy_players:
            verb = "is" if len(busy_players) == 1 else "are"
            mentions = ", ".join(p.mention for p in busy_players)
            await ctx.followup.send(
                fmt("permissions.players_in_other_game", mentions=mentions, verb=verb),
                ephemeral=True
            )
            log.info("Game start denied because one or more queued players are already in another active game. "
                     f"{contextify(ctx)}")
            return

        total_players = len(self.all_players())
        player_count = resolve_player_count(self.game)
        if isinstance(player_count, list):
            if total_players not in player_count:
                await ctx.followup.send(get("queue.bot_too_many_for_game"), ephemeral=True)
                return
        elif isinstance(player_count, int) and total_players != player_count:
            await ctx.followup.send(get("queue.bot_too_many_for_game"), ephemeral=True)
            return

        role_mode = getattr(self.game, "role_mode", RoleMode.NONE)
        if role_mode == RoleMode.CHOSEN:
            if self.has_bots:
                await ctx.followup.send(get("queue.role_chosen_no_bots"), ephemeral=True)
                return
            if len(self._specs) + len(self.all_players()) > 4:
                await ctx.followup.send(get("queue.role_chosen_ui_overflow"), ephemeral=True)
                return
            pr = getattr(self.game, "player_roles", None)
            if not pr or len(pr) != len(self.all_players()):
                await ctx.followup.send(get("queue.bot_too_many_for_game"), ephemeral=True)
                return
            for p in self.queued_players:
                if p.id not in self.role_selections:
                    await ctx.followup.send(get("queue.role_all_must_select"), ephemeral=True)
                    return
            vr = self.game.validate_role_selection(self.role_selections)
            if vr is not True:
                await ctx.followup.send(str(vr), ephemeral=True)
                return

        # The matchmaking was successful!
        self.outcome = True

        log.debug(f"Game successfully started by {player}!"
                  f"{contextify(ctx)}")
        # Start the GameInterface

        loading_message = Message(
            Container(
                TextDisplay(get_emoji_string("loading")),
            )
        )
        await self.message.edit(**loading_message.to_edit_kwargs())
        await successful_matchmaking(interface=self)


async def successful_matchmaking(interface: MatchmakingInterface) -> None:
    """
    Callback called by MatchmakingInterface when the game is successfully started
    Sets up and registers a new GameInterface.
    :param interface: MatchmakingInterface that will be registered as a GameInterface by this function
    :return: Nothing
    """
    message = interface.message
    sm_log = logging.getLogger(f"{LOGGING_ROOT}.successful_matchmaking")
    try:
        await _successful_matchmaking_impl(interface)
    except Exception:
        sm_log.exception("successful_matchmaking failed")
        try:
            error_container = ErrorContainer(
                ctx=None,
                what_failed=get("system_error.internal_what_failed"),
                reason=None,
            )
            error_message = Message(
                Container(
                    TextDisplay(container_to_markdown(error_container) or get("system_error.internal_what_failed")),
                    accent_color=ERROR_COLOR,
                )
            )
            await message.edit(**error_message.to_edit_kwargs())
        except Exception:
            pass


async def _successful_matchmaking_impl(interface: MatchmakingInterface) -> None:
    # Extract class variables
    game_class = interface.game
    rated = interface.rated
    players = interface.queued_players
    all_players_candidate = None
    try:
        if hasattr(interface, "all_players") and callable(interface.all_players):
            all_players_candidate = interface.all_players()
    except Exception:
        all_players_candidate = None
    if isinstance(all_players_candidate, (list, tuple, set)):
        all_players = list(all_players_candidate)
    else:
        all_players = list(players)
    message = interface.message
    game_type = interface.game_type
    creator = interface.creator
    has_bots = any(getattr(p, "is_bot", False) for p in all_players)

    # Remove human players in this matchmaking from IN_MATCHMAKING
    for p in list(players):
        IN_MATCHMAKING.pop(p, None)

    CURRENT_MATCHMAKING.pop(message.id, None)  # Remove the MatchmakingInterface from the CURRENT_MATCHMAKING tracker

    # Set up a new GameInterface
    match_opts_payload = dict(interface.match_settings)
    new_game_id, match_public_code = db.database.create_game(
        game_name=game_type,
        guild_id=message.guild.id,
        participants=[player.id for player in all_players],
        is_rated=(rated and not has_bots),
        channel_id=message.channel.id,
        game_config={"match_options": match_opts_payload},
    )
    from utils.analytics import EventType, register_event

    register_event(
        EventType.GAME_STARTED,
        user_id=creator.id,
        guild_id=message.guild.id,
        game_type=game_type,
        match_id=new_game_id,
        metadata={"player_count": len(all_players), "rated": rated and not has_bots},
    )
    role_sel = None
    if getattr(game_class, "role_mode", RoleMode.NONE) == RoleMode.CHOSEN:
        role_sel = dict(interface.role_selections)
    game = GameInterface(
        game_type,
        message,
        creator,
        list(all_players),
        rated and not has_bots,
        new_game_id,
        match_options=match_opts_payload,
        match_public_code=match_public_code,
        role_selections=role_sel,
    )
    try:
        await game.setup()  # Setup thread and other stuff

        db.database.update_match_context(
            match_id=new_game_id,
            channel_id=message.channel.id,
            thread_id=game.thread.id
        )

        # Register the game to the channel it's in
        CURRENT_GAMES.update({game.thread.id: game})

        # Edit the status message with the SpectateView
        async def create_spectate_view():
            spectate_summary = (
                f"## {game.game.name}\n"
                f"Match `{game.match_public_code}`\n"
                f"{'Rated' if game.rated else 'Casual'} game\n"
                f"Players: {', '.join(p.mention for p in game.players)}"
            )
            await message.edit(
                view=SpectateView(
                    spectate_button_id=f"spectate/{game.thread.id}",
                    peek_button_id=f"peek/{game.thread.id}/{game.game_message.id}",
                    game_link=game.info_message.jump_url,
                    summary_text=spectate_summary,
                ),
            )

        asyncio.create_task(create_spectate_view())
        await game.display_game_state()  # Send the game display state
    except Exception:
        _sm = logging.getLogger(f"{LOGGING_ROOT}.successful_matchmaking")
        try:
            db.database.abandon_match(new_game_id, "interface_setup_failed")
        except Exception:
            _sm.exception("abandon_match failed after setup error")
        try:
            register_event(
                EventType.GAME_ABANDONED,
                user_id=creator.id,
                guild_id=message.guild.id,
                game_type=game_type,
                match_id=new_game_id,
                metadata={"phase": "interface_setup", "reason": "setup_failed"},
            )
        except Exception:
            pass
        th = getattr(game, "thread", None)
        if th is not None:
            CURRENT_GAMES.pop(th.id, None)
        raise


def _pre_match_mu_sigma(player: Any, game_type: str) -> tuple[float, float]:
    """Mu/sigma before rate(): InternalPlayer has per-game stats; in-game api.Player uses .mu/.sigma."""
    stat = getattr(player, game_type, None)
    if stat is not None and hasattr(stat, "mu"):
        return float(stat.mu), float(stat.sigma)
    if isinstance(player, Player):
        return float(player.mu), float(player.sigma)
    raise TypeError(
        f"Cannot read pre-match rating for {type(player).__name__!r} (game_type={game_type!r})"
    )


async def rating_groups_to_string(rankings: list[int], groups: list[dict[Any, trueskill.Rating]],
                                  game_type: str) \
        -> tuple[str, dict[int, dict[str, str | bool | int | Any]]]:
    """
    Converts the rankings and groups from a rated game into a string representing the outcome of the game.
    :param rankings: Rankings (format: list of places such as [1, 1, 2, 3] to correlate with groups)
    :param groups: groups (format: [{player: player_rating}] where player is a Player.py object and player_rating
     is an trueskill.Rating object
    :param game_type: The game type, used to extract the correct rating from the player.
    :return: String representing the outcome of the game (format:
    1. PlayerInFirst
    2T. PlayerInSecond
    2T. PlayerAlsoInSecond
    4. LastPlayer
    )
    """

    # Dictionary containing all data relevant to the ratings
    player_ratings = {}

    # Place tracking variables
    current_place = 1
    nums_current_place = 0
    matching = 0

    # Turn list of dictionaries into a list of all the keys from the dictionaries
    keys = [next(iter(p)) for p in groups]

    # Convert the list of dictionaries into one dictionary with all of the keys
    all_ratings = {list(p.keys())[0]: list(p.values())[0] for p in groups}

    for i, pre_rated_player in enumerate(keys):  # Loop

        # Logic for keeping track of place
        if rankings[i] == matching:  # Same place ID as last person
            # Update the number of people who got the current place ID
            nums_current_place += 1
        else:  # Different ID, update to new ID and reset nums_current_place
            current_place += nums_current_place
            matching = rankings[i]
            nums_current_place = 1

        # Extract starting and ending rating variables
        starting_mu, starting_sigma = _pre_match_mu_sigma(pre_rated_player, game_type)
        aftermath_mu, aftermath_sigma = all_ratings[pre_rated_player].mu, all_ratings[pre_rated_player].sigma

        # Change in ELO
        mu_delta = str(round(aftermath_mu - starting_mu))

        if not mu_delta.startswith("-"):  # Add a "+" to the delta if it isn't negative
            mu_delta = "+" + mu_delta

        # Add data for the player to player_ratings
        player_ratings.update({pre_rated_player.id: {"old_mu": round(starting_mu), "delta": mu_delta,
                                                     "place": current_place, "tied": rankings.count(rankings[i]) > 1,
                                                     "new_mu": aftermath_mu,
                                                     "old_sigma": starting_sigma,
                                                     "new_sigma": aftermath_sigma}})
    # Concatenate to
    # 1. PlayerOne 1 (+384)
    # 2. PlayerTwo 30 (+2)
    # 3. PlayerThreeWhoSucks 20 (-20)
    player_string = "\n".join([
        f"{player_ratings[p]['place']}{'T' if player_ratings[p]['tied'] else ''}."
        f"{LONG_SPACE_EMBED}<@{p}>{LONG_SPACE_EMBED}{player_ratings[p]['old_mu']}"
        f"{LONG_SPACE_EMBED}({player_ratings[p]['delta']})"
        for p in player_ratings])

    # Return both the concatenated string AND the rating dictionary, as it is needed for the game_over function
    return player_string, player_ratings


async def non_rated_groups_to_string(rankings: list[int], groups: list[InternalPlayer]) -> str:
    """
    Create the string representing the groups for the game over screen
    :param rankings: Rankings: format [0, 1, 1, 2] for first place, two tied for 2nd, and 3rd. Corresponds to groups
    :param groups: Groups: format [list of players], places correspond to places in rankings
    :return: string of the groups formatted to display
    """

    # Output list to concatenate
    player_ratings = []

    # Loop variables
    current_place = 1
    nums_current_place = 0
    matching = 0

    # Loop through players
    for i, pre_rated_player in enumerate(groups):
        # Ranking of current player = last player ranked, so increment the number of people
        if rankings[i] == matching:
            nums_current_place += 1
        # New ranking
        else:
            current_place += nums_current_place  # Add number of people who were in previous ranking position
            matching = rankings[i]  # Now matching current player's ranking ID
            nums_current_place = 1

        # Check if tied
        show_tied = ""
        if rankings.count(rankings[i]) > 1:  # More than one player tied for same score
            show_tied = 'T'  # Display "T" (1T.)

        # Add format PLACE[TIED].   MENTION
        player_ratings.append(f"{current_place}{show_tied}.{LONG_SPACE_EMBED}{pre_rated_player.mention}")
    return "\n".join(player_ratings)  # concatenate and return


async def game_over(interface: GameInterface, outcome: str | InternalPlayer | list[list[InternalPlayer]]) -> None:
    """
    Callback called by GameInterface when the game is over. Easily the most technically complicated function
    in the entire API

    :param interface: GameInterface that the game_over was triggered by
    :param outcome: outcome of the game. There are three possibilities: string for error,
     one player who won (all other players lost), or a list of list of players formatted like this:
     [[p1, p2], [p3], [p4]] indicates p1 and p2 tied, p3 got third, p4 got fourth
    :return: Nothing
    """

    # Extract class variables
    interface.ending_game = True  # Prevent moves from being attempted after game is over
    game_type = interface.game_type
    thread = interface.thread
    outbound_message = interface.status_message
    rated = interface.rated
    players = interface.players
    game_id = interface.game_id

    # TrueSkill environment from the DB-backed game registry (bootstrapped from the live game class at startup)
    ts = get_trueskill_parameters(game_type)
    sigma = MU * ts["sigma"]
    beta = MU * ts["beta"]
    tau = MU * ts["tau"]
    draw = ts["draw"]

    # mpmath backend = near infinite floating point precision
    environment = trueskill.TrueSkill(mu=MU, sigma=sigma, beta=beta, tau=tau, draw_probability=draw,
                                      backend="mpmath")

    # There are three cases: str (error) Player (one person won) list[list[Player]] (detailed ranking)
    if isinstance(outcome, str):  # Error
        game_over_container = ErrorContainer(what_failed=get("game.error_during_move"), reason=outcome)
        error_message = Message(
            Container(
                TextDisplay(container_to_markdown(game_over_container) or str(outcome)),
                accent_color=ERROR_COLOR,
            )
        )
        await outbound_message.edit(**error_message.to_edit_kwargs())
        await interface.await_pending_ui_tasks()
        await thread.edit(locked=True, archived=True, reason=get("threads.game_crashed"))
        await thread.send(**container_send_kwargs(game_over_container))
        try:
            from utils.analytics import EventType, register_event

            register_event(
                EventType.GAME_ABANDONED,
                guild_id=thread.guild.id if thread.guild else None,
                game_type=game_type,
                match_id=game_id,
                metadata={"phase": "game_over_error", "detail": str(outcome)[:300]},
            )
        except Exception:
            pass
        return

    if rated:
        if isinstance(outcome, Player):  # Somebody won, everybody else lost. No way of comparison (tic-tac-toe)
            # Winner's rating
            winner = environment.create_rating(outcome.mu, outcome.sigma)

            # All the losers
            losers = [{p: environment.create_rating(*_pre_match_mu_sigma(p, game_type))}
                      for p in players if p != outcome]

            rating_groups = [{InternalPlayer(ratings={game_type: {"mu": outcome.mu, "sigma": outcome.sigma}},
                                             user=None, metadata={}, id=outcome.id): winner},
                             *losers]  # Make the rating groups, cast Player to InternalPlayer
            rankings = [0, *[1 for _ in range(len(players) - 1)]]  # Rankings = [0, 1, 1, ..., 1] for this case

        else:  # More generic position placement
            # Format:
            # [[p1, p2], [p3], [p4]] indicates p1 and p2 tied, p3 got third, p4 got fourth
            # What if there are teams? screw you

            current_ranking = 0
            rankings = []
            rating_groups = []
            for placement in outcome:
                for player in placement:
                    rankings.append(current_ranking)
                    rating_groups.append({player: environment.create_rating(player.mu, player.sigma)})
                current_ranking += 1

        # Rerate the groups
        adjusted_rating_groups = environment.rate(rating_groups=rating_groups, ranks=rankings)
        player_string, player_ratings = await rating_groups_to_string(rankings, adjusted_rating_groups, game_type)
        logging.getLogger(LOGGING_ROOT).debug(
            "rated game_over: rankings=%s player_ratings_keys=%s",
            rankings,
            list(player_ratings.keys()) if player_ratings else None,
        )
        ratings = {}
        for player in player_ratings:
            data = player_ratings[player]
            new_mu = data["new_mu"]
            new_sigma = data["new_sigma"]
            ratings.update({player: {"uid": player,
                                     "new_mu": new_mu,
                                     "new_sigma": new_sigma,
                                     "mu_delta": new_mu - data["old_mu"],
                                     "sigma_delta": new_sigma - data["old_sigma"],
                                     "ranking": data.get("ranking",
                                                         rankings[list(player_ratings.keys()).index(player)] + 1)}})

        db.database.end_game(match_id=game_id, game_name=game_type, rating_updates=ratings, final_scores=None)


    else:  # Non-rated game

        # In case of impossible fail: no rankings
        rankings = []
        groups = []

        if isinstance(outcome, Player):
            groups = [outcome, *[p for p in players if p != outcome]]  # Make the rating groups
            rankings = [0, *[1 for _ in range(len(players) - 1)]]  # Rankings = [0, 1, 1, ..., 1] for this case

        elif isinstance(outcome, list):
            current_ranking = 0
            rankings = []
            groups = []
            for placement in outcome:
                for player in placement:
                    rankings.append(current_ranking)
                    groups.append(player)
                current_ranking += 1

        player_string = await non_rated_groups_to_string(rankings, groups)

    outcome_summaries: dict[int, str] | None = None
    try:
        fn = getattr(interface.game, "match_summary", None)
        if callable(fn):
            raw = fn(outcome)
            if isinstance(raw, dict):
                parsed: dict[int, str] = {}
                for k, v in raw.items():
                    try:
                        kid = int(k)
                    except (TypeError, ValueError):
                        continue
                    s = str(v).strip()
                    if s:
                        parsed[kid] = s
                outcome_summaries = parsed or None
    except Exception:
        outcome_summaries = None

    outcome_global_summary: str | None = None
    try:
        gfn = getattr(interface.game, "match_global_summary", None)
        if callable(gfn):
            gs = gfn(outcome)
            if gs is not None:
                outcome_global_summary = str(gs).strip() or None
    except Exception:
        outcome_global_summary = None

    if outcome_summaries is not None or outcome_global_summary:
        db.database.merge_match_metadata_outcome_display(
            game_id,
            summaries=outcome_summaries,
            global_summary=outcome_global_summary,
        )

    try:
        from utils.analytics import EventType, register_event

        register_event(
            EventType.GAME_COMPLETED,
            user_id=getattr(interface.creator, "id", None),
            guild_id=thread.guild.id if thread.guild else None,
            game_type=game_type,
            match_id=game_id,
            metadata={
                "rated": bool(rated),
                "has_outcome_summary": outcome_summaries is not None
                                       or outcome_global_summary is not None,
            },
        )
    except Exception:
        pass

    for p in players:  # Players playing this game are no longer in the game... it's over lol
        IN_GAME.pop(p, None)

    CURRENT_GAMES.pop(thread.id)  # Remove this game from the CURRENT_GAMES tracker

    # Create GameOverContainer to show in the status and info messages
    game_over_container = GameOverContainer(
        rankings=player_string,
        game_name=interface.game.name,
        players=players,
        outcome_summaries=outcome_summaries,
        outcome_global_summary=outcome_global_summary,
    )

    # Send the container summary to overview / game thread
    await thread.send(**container_send_kwargs(game_over_container))
    await outbound_message.edit(view=RematchView(game_id, summary_text=container_to_markdown(game_over_container)))

    await interface.await_pending_ui_tasks()

    # Close the game thread
    await thread.edit(locked=True, archived=True, reason=get("threads.game_over"))

    # # If the game is rated, perform the relatively intensive task of updating the DB rankings
    # if rated:
    #     for player_id in player_ratings:  # Every rated player, post new ratings in the database
    #         player_data = player_ratings[player_id]
    #         update_player(game_type, InternalPlayer(mu=player_data["new_mu"],
    #                                                 sigma=player_data["new_sigma"],
    #                                                 user=discord.Object(id=player_id)))
    #
    #     update_db_rankings(game_type)  # Update ranking db variable
