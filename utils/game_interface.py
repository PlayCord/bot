"""Discord game-session interface implementation."""

import asyncio
import importlib
import inspect
import random
import typing
from typing import Any

import discord

from api.Game import PlayerOrder
from api.MessageComponents import Container, Message, TextDisplay
from api.Player import Player
from api.Response import Response
from configuration.constants import (
    BUTTON_PREFIX_PEEK,
    BUTTON_PREFIX_SPECTATE,
    EPHEMERAL_DELETE_AFTER,
    GAME_MSG_ALREADY_OVER,
    GAME_TYPES,
    INFO_COLOR,
    IN_GAME,
    MU,
    PERMISSION_MSG_NOT_YOUR_TURN,
    TEXTIFY_CURRENT_GAME_TURN,
    UI_MESSAGE_DELETE_DELAY,
)
from utils import database as db
from utils.analytics import Timer, register_event
from utils.containers import (
    ErrorContainer,
    LoadingContainer,
    container_send_kwargs,
    container_to_markdown,
)
from utils.conversion import contextify, textify
from utils.database import InternalPlayer, internal_player_to_player
from utils.discord_utils import followup_send
from utils.interface_lifecycle import game_over
from utils.interface_rendering import build_game_info_message, build_game_status_view
from utils.interfaces import synthetic_bot_name_from_id
from utils.locale import fmt, get
from utils.logging_config import get_logger
from utils.models import EventType
from utils.trueskill_params import get_trueskill_parameters


class GameInterface:
    """
    A class that handles the interface between the game and discord

    Discord <--> Bot <--> GameInterface <--> Game
    """

    def __init__(
        self,
        game_type: str,
        status_message: discord.InteractionMessage,
        creator: discord.User,
        players: list[InternalPlayer | Player],
        rated: bool,
        game_id: int,
        match_options: dict[str, typing.Any] | None = None,
        match_public_code: str | None = None,
        role_selections: dict[int, str] | None = None,
    ) -> None:
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
        self.match_public_code = (
            match_public_code if match_public_code else str(game_id)
        )
        self.status_message = status_message
        self.match_options = dict(match_options) if match_options else {}
        # The game type
        self.game_type = game_type
        self.logger = get_logger("interfaces.game").getChild(game_type)
        # Who created the lobby
        self.creator = creator

        # Get the game class to check player_order setting
        self.module = importlib.import_module(GAME_TYPES[game_type][0])  # Game module
        game_class = getattr(self.module, GAME_TYPES[game_type][1])

        # Order players based on game's player_order setting
        player_order = getattr(game_class, "player_order", PlayerOrder.RANDOM)

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
        self.game_message = (
            None  # The message representing the game after self.setup() is called
        )
        self.info_message = (
            None  # The message showing game info, whose turn, and what players.
        )
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
                        name=getattr(
                            participant,
                            "name",
                            synthetic_bot_name_from_id(participant.id),
                        ),
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
        self.forfeited_player_ids: set[int] = set()

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
        log.debug(
            f"Setting up game interface for a new game. matchmaker ID: {self.status_message.id}"
        )
        rated_prefix = get("queue.thread_rated_prefix") if self.rated else ""

        game_thread = await self.status_message.channel.create_thread(  # Create the private thread.
            name=fmt(
                "queue.thread_name",
                prefix=rated_prefix,
                game=self.game.name,
                match_code=self.match_public_code,
            ),
            type=discord.ChannelType.private_thread,
            invitable=False,
        )  # Don't allow people to add themselves

        for player in self.players:
            if hasattr(player, "user") and player.user is not None:
                try:
                    await game_thread.add_user(player.user)
                except discord.HTTPException as e:
                    log.warning("add_user failed for %s: %s", player.user.id, e)

        loading_message = Message(
            container_to_markdown(LoadingContainer().remove_footer())
        )

        # Set the thread and game message in the class
        self.thread = game_thread

        self.info_message = await self.thread.send(
            **container_send_kwargs(LoadingContainer().remove_footer())
        )
        self.game_message = await self.thread.send(
            **container_send_kwargs(LoadingContainer().remove_footer())
        )
        log.debug(
            f"Finished game setup for a new game in {setup_timer.stop()}ms."
            f" matchmaker ID: {self.status_message.id} game ID: {self.thread.id}"
        )

    async def move_by_command(
        self,
        ctx: discord.Interaction,
        name: str,
        arguments: dict[str, typing.Any],
        current_turn_required: bool = True,
    ) -> None:
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
        function_to_call = self._resolve_move_callable(name)
        actor = await self._get_move_actor(
            ctx=ctx,
            interaction_kind="slash_command",
            command_name=name,
            logger_name="move[command]",
        )
        if actor is None:
            return
        await self._run_move_interaction(
            ctx=ctx,
            logger_name="move[command]",
            interaction_kind="slash_command",
            command_name=name,
            python_callback_name=function_to_call,
            current_turn_required=current_turn_required,
            call_move=lambda: getattr(self.game, function_to_call)(actor, **arguments),
            persist_args=dict(arguments),
            delete_original_response_when_empty=True,
        )

    async def _guard_move_interaction(
        self,
        *,
        ctx: discord.Interaction,
        interaction_kind: str,
        command_name: str,
        current_turn_required: bool,
        log,
    ) -> bool:
        if ctx.user.id in self.forfeited_player_ids:
            self._track_move_event(
                EventType.MOVE_REJECTED,
                ctx=ctx,
                interaction_kind=interaction_kind,
                command_name=command_name,
                reason="already_forfeited",
            )
            await followup_send(
                ctx,
                get("forfeit.already_forfeited"),
                ephemeral=True,
                delete_after=EPHEMERAL_DELETE_AFTER,
            )
            return False

        if self.game.is_game_finished():
            self._track_move_event(
                EventType.MOVE_REJECTED,
                ctx=ctx,
                interaction_kind=interaction_kind,
                command_name=command_name,
                reason="game_already_over",
            )
            message = await followup_send(
                ctx, content=GAME_MSG_ALREADY_OVER, ephemeral=True
            )
            await message.delete(delay=UI_MESSAGE_DELETE_DELAY)
            return False

        self.current_turn = self.game.current_turn()
        if getattr(self.current_turn, "is_bot", False):
            self._track_move_event(
                EventType.MOVE_REJECTED,
                ctx=ctx,
                interaction_kind=interaction_kind,
                command_name=command_name,
                reason="bot_turn",
            )
            message = await followup_send(
                ctx, content=PERMISSION_MSG_NOT_YOUR_TURN, ephemeral=True
            )
            await message.delete(delay=UI_MESSAGE_DELETE_DELAY)
            return False

        if ctx.user.id != self.current_turn.id and current_turn_required:
            log.debug(
                "current_turn_required failed (expected=%s actual=%s) context=%s",
                getattr(self.current_turn, "id", None),
                getattr(ctx.user, "id", None),
                contextify(ctx),
            )
            self._track_move_event(
                EventType.MOVE_REJECTED,
                ctx=ctx,
                interaction_kind=interaction_kind,
                command_name=command_name,
                reason="not_your_turn",
            )
            message = await followup_send(
                ctx, content=PERMISSION_MSG_NOT_YOUR_TURN, ephemeral=True
            )
            await message.delete(delay=UI_MESSAGE_DELETE_DELAY)
            return False

        return True

    async def _send_interaction_move_response(
        self,
        *,
        ctx: discord.Interaction,
        move_response: Any,
        delete_original_response_when_empty: bool,
        log,
        command_name: str,
    ) -> None:
        if move_response is None:
            if delete_original_response_when_empty:
                try:
                    await ctx.delete_original_response()
                except Exception:
                    log.warning(
                        "delete_original_response failed name=%r context=%s",
                        command_name,
                        contextify(ctx),
                        exc_info=True,
                    )
            return

        send_move, set_delete_hook = move_response.generate_message(
            ctx.followup.send,
            self.thread.id,
            enable_view_components=False,
        )
        sent_message = await send_move
        if sent_message is False and delete_original_response_when_empty:
            try:
                await ctx.delete_original_response()
            except Exception:
                log.warning(
                    "delete_original_response failed name=%r context=%s",
                    command_name,
                    contextify(ctx),
                    exc_info=True,
                )
            return

        hook = set_delete_hook(sent_message)
        if hook:
            await hook

    async def _get_move_actor(
        self,
        *,
        ctx: discord.Interaction,
        interaction_kind: str,
        command_name: str,
        logger_name: str,
    ) -> Player | None:
        log = self.logger.getChild(logger_name)
        if ctx.guild is None:
            self._track_move_event(
                EventType.MOVE_INVALID,
                ctx=ctx,
                interaction_kind=interaction_kind,
                command_name=command_name,
                reason="missing_guild_context",
            )
            await self._send_move_processing_error(ctx)
            return None
        internal_player = db.database.get_player(ctx.user, ctx.guild.id)
        if internal_player is None:
            log.warning(
                "Missing InternalPlayer for user=%s guild=%s command=%s",
                getattr(ctx.user, "id", None),
                ctx.guild.id,
                command_name,
            )
            self._track_move_event(
                EventType.MOVE_INVALID,
                ctx=ctx,
                interaction_kind=interaction_kind,
                command_name=command_name,
                reason="missing_player_record",
            )
            await followup_send(
                ctx,
                get("queue.couldnt_connect_db"),
                ephemeral=True,
                delete_after=EPHEMERAL_DELETE_AFTER,
            )
            return None
        return internal_player_to_player(internal_player, self.game_type)

    async def _run_move_interaction(
        self,
        *,
        ctx: discord.Interaction,
        logger_name: str,
        interaction_kind: str,
        command_name: str,
        python_callback_name: str,
        current_turn_required: bool,
        call_move: typing.Callable[[], Any],
        persist_args: dict[str, Any],
        delete_original_response_when_empty: bool = False,
    ) -> None:
        log = self.logger.getChild(logger_name)
        if self.ending_game:
            log.warning(
                "Denied interaction command=%r because game is ending. context=%s",
                command_name,
                contextify(ctx),
            )
            return

        async with self.processing_move:
            log.debug(
                "Processing move command=%r interaction_kind=%s context=%s",
                command_name,
                interaction_kind,
                contextify(ctx),
            )
            if not await self._guard_move_interaction(
                ctx=ctx,
                interaction_kind=interaction_kind,
                command_name=command_name,
                current_turn_required=current_turn_required,
                log=log,
            ):
                return

            try:
                move_response: Response | None = call_move()
            except Exception:
                log.exception(
                    "move callback failed command=%r context=%s",
                    command_name,
                    contextify(ctx),
                )
                self._track_move_event(
                    EventType.MOVE_INVALID,
                    ctx=ctx,
                    interaction_kind=interaction_kind,
                    command_name=command_name,
                    reason="callback_exception",
                )
                await self._send_move_processing_error(ctx)
                return

            try:
                await self._send_interaction_move_response(
                    ctx=ctx,
                    move_response=move_response,
                    delete_original_response_when_empty=delete_original_response_when_empty,
                    log=log,
                    command_name=command_name,
                )
            except Exception:
                log.exception(
                    "move UI phase failed command=%r context=%s",
                    command_name,
                    contextify(ctx),
                )
                self._track_move_event(
                    EventType.MOVE_INVALID,
                    ctx=ctx,
                    interaction_kind=interaction_kind,
                    command_name=command_name,
                    reason="ui_send_failure",
                )
                await self._send_move_processing_error(ctx)
                return

            try:
                await self._move_postamble(
                    ctx=ctx,
                    move_response=move_response,
                    python_callback_name=python_callback_name,
                    persist_user_id=ctx.user.id,
                    persist_args=persist_args,
                    interaction_kind=interaction_kind,
                )
            except Exception:
                log.exception(
                    "move postamble failed command=%r context=%s",
                    command_name,
                    contextify(ctx),
                )
                self._track_move_event(
                    EventType.MOVE_INVALID,
                    ctx=ctx,
                    interaction_kind=interaction_kind,
                    command_name=command_name,
                    reason="postamble_failure",
                )
                await self._send_move_processing_error(ctx)

    @staticmethod
    def _convert_typed_move_arguments(
        callback_function: typing.Callable, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        signature = inspect.signature(callback_function).parameters
        converted: dict[str, Any] = {}
        for arg, value in arguments.items():
            argument_type = signature[arg].annotation
            if argument_type is int:
                converted[arg] = int(value)
            elif argument_type is float:
                converted[arg] = float(value)
            else:
                converted[arg] = value
        return converted

    def _resolve_move_callable(self, command_name: str) -> str:
        callback = None
        for command in self.game.moves:
            if command.name == command_name:
                callback = command.callback
                break
        return command_name if callback is None else callback

    async def _send_move_processing_error(self, ctx: discord.Interaction) -> None:
        await followup_send(
            ctx, content=get("move.unexpected_processing_error"), ephemeral=True
        )

    def _track_move_event(
        self,
        event_type: Any,
        *,
        ctx: discord.Interaction | None,
        interaction_kind: str,
        command_name: str,
        reason: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        metadata = {
            "interaction_kind": interaction_kind,
            "command_name": command_name,
        }
        if reason:
            metadata["reason"] = reason
        if extra:
            metadata.update(extra)
        guild_id = None
        if self.thread is not None and self.thread.guild is not None:
            guild_id = self.thread.guild.id
        elif ctx is not None and ctx.guild is not None:
            guild_id = ctx.guild.id
        register_event(
            event_type,
            user_id=(
                getattr(getattr(ctx, "user", None), "id", None)
                if ctx is not None
                else None
            ),
            guild_id=guild_id,
            game_type=self.game_type,
            match_id=self.game_id,
            metadata=metadata,
        )

    def _replay_sink_from_game(self, event: dict) -> None:
        try:
            if not isinstance(event, dict):
                return
            row = dict(event)
            row.setdefault("type", "game_event")
            db.database.append_replay_event(self.game_id, row)
        except Exception as e:
            self.logger.getChild("replay").warning(
                "append_replay_event failed: %s", e, exc_info=True
            )

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
        command_name = _cmd.name if _cmd is not None else python_callback_name
        game_affecting = _cmd.is_game_affecting if _cmd is not None else True
        should_persist = self._should_persist_move_replay(move_response, _cmd)
        response_type = (
            type(move_response).__name__ if move_response is not None else "None"
        )
        if not game_affecting:
            self._track_move_event(
                EventType.MOVE_VALID,
                ctx=ctx,
                interaction_kind=interaction_kind,
                command_name=command_name,
                reason="non_affecting_command",
                extra={"game_affecting": False, "response_type": response_type},
            )
        elif should_persist:
            self._track_move_event(
                EventType.MOVE_VALID,
                ctx=ctx,
                interaction_kind=interaction_kind,
                command_name=command_name,
                extra={"game_affecting": True, "response_type": response_type},
            )
        else:
            self._track_move_event(
                EventType.MOVE_INVALID,
                ctx=ctx,
                interaction_kind=interaction_kind,
                command_name=command_name,
                reason="move_not_applied",
                extra={
                    "game_affecting": True,
                    "response_type": response_type,
                    "record_replay": bool(
                        getattr(move_response, "record_replay", False)
                    ),
                },
            )
        if should_persist:
            self._persist_move_and_replay(
                python_callback_name, persist_user_id, persist_args, interaction_kind
            )
        if (outcome := self.game.outcome()) is not None:
            log.debug(
                "Received not-null game outcome: %r context: %s",
                outcome,
                contextify(ctx),
            )
            message = await followup_send(
                ctx, content=get("game.over_short"), ephemeral=True
            )
            await message.delete(delay=UI_MESSAGE_DELETE_DELAY)
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
        if isinstance(move_response, Response) and getattr(
            move_response, "record_replay", False
        ):
            return True
        return False

    @staticmethod
    def _json_safe_for_move(value: Any) -> Any:
        if value is None or isinstance(value, (bool, int, float, str)):
            return value
        if isinstance(value, dict):
            return {
                str(k): GameInterface._json_safe_for_move(v) for k, v in value.items()
            }
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
            self.logger.getChild("replay").warning(
                "persist move failed: %s", e, exc_info=True
            )

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
                if self.game.is_game_finished():
                    return
                self.current_turn = self.game.current_turn()
                if not getattr(self.current_turn, "is_bot", False):
                    return

                bot_difficulty = getattr(self.current_turn, "bot_difficulty", None)
                available_bots = getattr(self.game, "bots", {})
                bot_definition = available_bots.get(bot_difficulty)
                if bot_definition is None:
                    await self.thread.send(
                        fmt("game.bot_failed_move", player=self.current_turn.mention)
                    )
                    return

                callback_name = (
                    bot_definition.callback
                    if bot_definition.callback is not None
                    else bot_difficulty
                )
                callback = getattr(self.game, callback_name, None)
                if callback is None:
                    await self.thread.send(
                        fmt("game.bot_failed_move", player=self.current_turn.mention)
                    )
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
                        await self.thread.send(
                            fmt(
                                "game.bot_failed_move", player=self.current_turn.mention
                            )
                        )
                        return
                    function_name = self._resolve_move_callable(command_name)
                    replay_python_fn = function_name
                    replay_args = dict(command_arguments)
                    move_response = getattr(self.game, function_name)(
                        self.current_turn, **command_arguments
                    )
                elif isinstance(bot_result, tuple) and len(bot_result) == 2:
                    command_name, command_arguments = bot_result
                    function_name = self._resolve_move_callable(command_name)
                    replay_python_fn = function_name
                    replay_args = dict(command_arguments)
                    move_response = getattr(self.game, function_name)(
                        self.current_turn, **command_arguments
                    )
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
                    self._persist_move_and_replay(
                        replay_python_fn, uid, replay_args, "bot"
                    )

            if (outcome := self.game.outcome()) is not None:
                await game_over(self, outcome)
                return
        except Exception as err:
            log.error(f"Bot turn failed with error {err!r}", exc_info=True)
            if self.thread is not None:
                try:
                    await self.thread.send(get("move.unexpected_processing_error"))
                except Exception:
                    await self.thread.send(
                        fmt(
                            "game.bot_failed_move",
                            player=getattr(self.current_turn, "mention", "Bot"),
                        )
                    )
        finally:
            self.processing_bot_turn = False

    async def move_by_button(
        self,
        ctx: discord.Interaction,
        name,
        arguments: dict[str, typing.Any],
        current_turn_required: bool = True,
    ) -> None:
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
        actor = await self._get_move_actor(
            ctx=ctx,
            interaction_kind="button",
            command_name=name,
            logger_name="move[button]",
        )
        if actor is None:
            return

        callback_function = getattr(self.game, name)
        try:
            converted_arguments = self._convert_typed_move_arguments(
                callback_function, arguments
            )
        except Exception:
            log = self.logger.getChild("move[button]")
            log.exception(
                "move_by_button argument conversion failed name=%r arguments=%r context=%s",
                name,
                arguments,
                contextify(ctx),
            )
            self._track_move_event(
                EventType.MOVE_INVALID,
                ctx=ctx,
                interaction_kind="button",
                command_name=name,
                reason="argument_conversion_failure",
            )
            await self._send_move_processing_error(ctx)
            return
        await self._run_move_interaction(
            ctx=ctx,
            logger_name="move[button]",
            interaction_kind="button",
            command_name=name,
            python_callback_name=name,
            current_turn_required=current_turn_required,
            call_move=lambda: callback_function(actor, **converted_arguments),
            persist_args=dict(converted_arguments),
        )

    async def move_by_select(
        self, ctx: discord.Interaction, name: str, current_turn_required: bool = True
    ):
        """
        Select-menu moves: the game's callback receives ``(player, ctx.data['values'])``.
        Handlers must be synchronous like ``move_by_button``.
        """
        actor = await self._get_move_actor(
            ctx=ctx,
            interaction_kind="select",
            command_name=name,
            logger_name="move[select]",
        )
        if actor is None:
            return

        values = ctx.data.get("values", []) if isinstance(ctx.data, dict) else []
        callback_function = getattr(self.game, name)
        await self._run_move_interaction(
            ctx=ctx,
            logger_name="move[select]",
            interaction_kind="select",
            command_name=name,
            python_callback_name=name,
            current_turn_required=current_turn_required,
            call_move=lambda: callback_function(actor, values),
            persist_args={"values": values},
        )

    def _build_info_message(self, turn_description: str) -> Message:
        return build_game_info_message(
            players=self.players,
            game_type=self.game_type,
            turn_description=turn_description,
            game_name=self.game.name,
            current_turn=self.current_turn,
        )

    def _build_status_view(self):
        return build_game_status_view(
            game=self.game,
            game_type=self.game_type,
            rated=self.rated,
            players=self.players,
            current_turn=self.current_turn,
            thread_id=self.thread.id,
            game_message_id=self.game_message.id,
            info_jump_url=(
                self.info_message.jump_url if self.info_message is not None else None
            ),
            peek_button_prefix=BUTTON_PREFIX_PEEK,
            spectate_button_prefix=BUTTON_PREFIX_SPECTATE,
        )

    def _advance_past_forfeited_players(self) -> None:
        if not self.forfeited_player_ids:
            return
        turn_index = getattr(self.game, "turn", None)
        players = getattr(self.game, "players", None)
        if (
            not isinstance(turn_index, int)
            or not isinstance(players, list)
            or not players
        ):
            return
        for _ in range(len(players)):
            current = players[turn_index % len(players)]
            if getattr(current, "id", None) not in self.forfeited_player_ids:
                self.game.turn = turn_index % len(players)
                return
            turn_index += 1

    async def _sync_thread_messages(self) -> None:
        log = self.logger.getChild("_sync_thread_messages")
        try:
            desired = {
                item.key: item.content for item in (self.game.thread_messages() or [])
            }

            for key in list(self._thread_messages):
                if key not in desired:
                    try:
                        await self._thread_messages[key].delete()
                    except discord.HTTPException:
                        pass
                    self._thread_messages.pop(key, None)

            for key, message in desired.items():
                if key in self._thread_messages:
                    await self._thread_messages[key].edit(
                        **message.to_edit_kwargs(self.thread.id)
                    )
                else:
                    self._thread_messages[key] = await self.thread.send(
                        **message.to_send_kwargs(self.thread.id)
                    )
        except Exception as e:
            log.exception("Failed to sync thread messages")

    async def _dispatch_private_updates(self, ctx: discord.Interaction) -> None:
        actor = (
            db.database.get_player(ctx.user, ctx.guild.id)
            if ctx.guild is not None
            else None
        )
        if actor is not None:
            private_message = self.game.player_state(
                internal_player_to_player(actor, self.game_type)
            )
            if private_message is not None:
                await followup_send(
                    ctx,
                    **private_message.to_send_kwargs(self.thread.id),
                    ephemeral=True,
                )

        if getattr(self.game, "notify_on_turn", False):
            turn_player = self.game.current_turn()
            if getattr(turn_player, "id", None) == getattr(ctx.user, "id", None):
                await followup_send(
                    ctx, self.game.turn_notification(turn_player), ephemeral=True
                )

    async def display_game_state(self) -> None:
        """
        Use the Game class (self.game) to get an updated version of the game state.
        :return: None
        """
        log = self.logger.getChild("display_game_state")
        update_timer = Timer().start()
        try:
            self.current_turn = self.game.current_turn()
            if getattr(self.current_turn, "id", None) in self.forfeited_player_ids:
                self._advance_past_forfeited_players()
                self.current_turn = self.game.current_turn()
            if getattr(self.current_turn, "is_bot", False):
                turn_description = fmt(
                    "game.bot_turn_computing", player=self.current_turn.mention
                )
            else:
                turn_description = textify(
                    TEXTIFY_CURRENT_GAME_TURN, {"player": self.current_turn.mention}
                )
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
                await self.game_message.edit(
                    **game_state.to_edit_kwargs(self.thread.id)
                )

            self._track_ui_task(edit_game_message())

            # Edit overview embed with new data
            async def edit_status_message():
                while self.status_message is None:
                    await asyncio.sleep(1)
                status_view, attachments = self._build_status_view()
                await self.status_message.edit(
                    view=status_view, attachments=attachments
                )

            self._track_ui_task(edit_status_message())

            log.debug(
                f"Finished game state update task in {update_timer.stop()}ms."
                f" game_id={self.thread.id} game_type={self.game_type}"
            )

            if (
                getattr(self.current_turn, "is_bot", False)
                and not self.ending_game
                and not self.processing_bot_turn
            ):
                asyncio.create_task(self.execute_bot_turn())

        except Exception as e:
            log.exception("Failed to display game state")
            self.ending_game = True

            # Determine what component failed
            if isinstance(
                e, ValueError
            ) and "maximum number of children exceeded" in str(e):
                what_failed = (
                    "Discord API: Message component limit exceeded (too many elements)"
                )
            elif "maximum number of children exceeded" in str(e):
                what_failed = "Discord API: Component limit exceeded"
            elif hasattr(e, "__module__") and "discord" in e.__module__:
                what_failed = f"Discord API: {type(e).__name__}"
            else:
                what_failed = f"Game Engine: {type(e).__name__}"

            error_embed = ErrorContainer(what_failed=what_failed, reason=str(e))
            error_message = Message(error_embed)

            try:
                await self.game_message.edit(
                    **error_message.to_edit_kwargs(self.thread.id)
                )
            except Exception:
                try:
                    await self.game_message.edit(
                        content="❌ An error occurred while updating the game display. The game has ended.",
                        embeds=[],
                        view=None,
                        attachments=[],
                    )
                except Exception:
                    log.exception("Failed to send error message to game_message")

    async def bump(self):
        self.game_message = await self.game_message.channel.send()

    async def forfeit_player(self, user_id: int) -> str:
        if user_id in self.forfeited_player_ids:
            return get("forfeit.already_forfeited")

        active_players = [
            p
            for p in self.players
            if getattr(p, "id", None) not in self.forfeited_player_ids
        ]
        forfeiting_player = next(
            (p for p in active_players if getattr(p, "id", None) == user_id), None
        )
        if forfeiting_player is None:
            return get("forfeit.not_in_game")

        self.forfeited_player_ids.add(user_id)

        # Log forfeit event to replay
        move_no = db.database.get_move_count(self.game_id) + 1
        forfeit_event = {
            "type": "forfeit",
            "move_number": move_no,
            "user_id": user_id,
            "player_name": forfeiting_player.mention,
            "is_game_affecting": True,
        }
        db.database.append_replay_event(self.game_id, forfeit_event)

        remaining = [p for p in active_players if getattr(p, "id", None) != user_id]
        if len(remaining) <= 1:
            winner = remaining[0] if remaining else forfeiting_player
            await game_over(self, winner)
            return fmt("forfeit.confirmed_loss", player=forfeiting_player.mention)

        self._advance_past_forfeited_players()
        await self.display_game_state()
        return fmt("forfeit.confirmed_skip", player=forfeiting_player.mention)
