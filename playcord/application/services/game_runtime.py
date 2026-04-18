"""New modular game runtime."""

from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, urlencode

import discord

from playcord import state as session_state
from playcord.games.api import (
    BinaryAsset,
    ButtonSpec,
    DeleteMessage,
    GameContext,
    GamePlugin,
    MessageLayout,
    OwnedMessage,
    SelectSpec,
    UpsertMessage,
)
from playcord.infrastructure.app_constants import (
    BUTTON_PREFIX_PEEK,
    BUTTON_PREFIX_SPECTATE,
)
from playcord.presentation.interactions.router import CustomId
from playcord.utils import database as db
from playcord.utils.containers import TEXT_DISPLAY_MAX
from playcord.utils.discord_utils import followup_send
from playcord.utils.locale import get
from playcord.utils.logging_config import get_logger

CURRENT_GAMES = session_state.CURRENT_GAMES
IN_GAME = session_state.IN_GAME

log = get_logger("game.runtime")


@dataclass(slots=True)
class RuntimeMoveResult:
    actions: tuple[Any, ...]
    finished: bool = False


class RuntimeView(discord.ui.LayoutView):
    """Game UI: components v2 (LayoutView + Container), like lobbies and help."""

    def __init__(self) -> None:
        super().__init__(timeout=None)


class GameRuntime:
    """Executes final API plugins and owns all bot-authored match messages."""

    def __init__(
        self,
        *,
        game_type: str,
        plugin_class: type[GamePlugin],
        overview_message: discord.Message,
        creator: discord.abc.User,
        players: list[Any],
        rated: bool,
        match_id: int,
        match_public_code: str,
        match_options: dict[str, Any] | None = None,
    ) -> None:
        self.game_type = game_type
        self.plugin_class = plugin_class
        self.plugin = plugin_class(
            players=list(players),
            match_options=match_options or {},
        )
        self.game = self.plugin
        # RNG / setup lines: plugins call ``log_replay_event``.
        self.plugin._replay_hook = self._plugin_replay_hook
        self.creator = creator
        self.players = list(players)
        self.rated = rated
        self.game_id = match_id
        self.match_public_code = match_public_code
        self.match_options = dict(match_options or {})
        self.status_message = overview_message
        self.thread: discord.Thread | None = None
        self.owned_messages: dict[str, discord.Message] = {}
        self._processing_move = asyncio.Lock()
        self.ending_game = False
        self._interrupt_started = False
        self.forfeited_player_ids: set[int] = set()
        self.logger = log.getChild(game_type)

    async def setup(self) -> None:
        thread_name = f"{self.plugin.metadata.name} - {self.match_public_code}"
        self.thread = await self.status_message.create_thread(name=thread_name)
        for player in self.players:
            player_id = getattr(player, "id", None)
            if player_id is not None:
                IN_GAME[int(player_id)] = self
            if not getattr(player, "is_bot", False) and hasattr(self.thread, "add_user"):
                member = getattr(player, "user", None)
                if member is not None:
                    try:
                        await self.thread.add_user(member)
                    except Exception:
                        self.logger.debug("Failed to add player %s to thread", player_id)
        CURRENT_GAMES[self.thread.id] = self
        await self.render_state()

    def build_context(self) -> GameContext:
        owned = []
        rows = []
        if hasattr(db.database, "list_bot_messages"):
            try:
                rows = db.database.list_bot_messages(self.game_id)
            except Exception:
                rows = []
        if rows:
            for row in rows:
                owned.append(
                    OwnedMessage(
                        key=row["message_key"],
                        purpose=row["purpose"],
                        discord_message_id=row["discord_message_id"],
                        channel_id=row["channel_id"],
                        metadata=dict(row.get("metadata") or {}),
                    )
                )
        else:
            for key, message in self.owned_messages.items():
                owned.append(
                    OwnedMessage(
                        key=key,
                        purpose="board" if key == "board" else "overview",
                        discord_message_id=message.id,
                        channel_id=message.channel.id,
                        metadata={},
                    )
                )
        return GameContext(
            match_id=self.game_id,
            game_key=self.game_type,
            players=list(self.players),
            match_options=dict(self.match_options),
            owned_messages=owned,
            latest_overview=getattr(self.status_message, "content", None),
        )

    async def render_state(self) -> None:
        await self._apply_actions(self.plugin.render(self.build_context()))

    async def display_game_state(self) -> None:
        await self.render_state()

    async def await_pending_ui_tasks(self) -> None:
        return None

    async def move_by_command(
        self,
        ctx: discord.Interaction,
        name: str,
        arguments: dict[str, Any],
        *,
        current_turn_required: bool = True,
    ) -> None:
        await self._apply_move(
            ctx,
            name=name,
            arguments=arguments,
            source="command",
            current_turn_required=current_turn_required,
        )

    async def move_by_button(
        self,
        ctx: discord.Interaction,
        name: str,
        arguments: dict[str, Any],
        *,
        current_turn_required: bool = True,
    ) -> None:
        await self._apply_move(
            ctx,
            name=name,
            arguments=arguments,
            source="button",
            current_turn_required=current_turn_required,
        )

    async def move_by_select(
        self,
        ctx: discord.Interaction,
        name: str,
        *,
        current_turn_required: bool = True,
    ) -> None:
        values = list((ctx.data or {}).get("values") or [])
        arguments = {"values": values}
        await self._apply_move(
            ctx,
            name=name,
            arguments=arguments,
            source="select",
            current_turn_required=current_turn_required,
        )

    async def handle_spectate(self, ctx: discord.Interaction) -> None:
        if self.thread is not None:
            await self.thread.add_user(ctx.user)
        await followup_send(ctx, get("success.spectating"), ephemeral=True)

    async def handle_peek(self, ctx: discord.Interaction) -> None:
        text = self.plugin.peek(self.build_context()) or get("success.already_participant")
        await followup_send(ctx, text, ephemeral=True)

    async def run_bot_turn_if_needed(self) -> None:
        outcome = self.plugin.outcome()
        if outcome is not None:
            await self.finish(outcome)
            return
        current = self.plugin.current_turn()
        if current is None or not getattr(current, "is_bot", False):
            return
        move = self.plugin.bot_move(current, ctx=self.build_context())
        if not move:
            return
        guild = self.thread.guild if self.thread is not None else None
        fake = type(
            "BotInteraction",
            (),
            {"user": current, "guild": guild, "channel": self.thread},
        )()
        await self._apply_bot_move(
            fake,
            name=str(move["move_name"]),
            arguments=dict(move.get("arguments", {})),
        )

    async def finish(self, outcome) -> None:
        from playcord.application.services.match_lifecycle import finish_match

        if self.ending_game:
            return
        self.ending_game = True
        await finish_match(self, outcome)

    async def _apply_bot_move(self, ctx: Any, *, name: str, arguments: dict[str, Any]) -> None:
        async with self._processing_move:
            actor = self._player_by_id(getattr(ctx.user, "id", None))
            if actor is None:
                return
            actions = self.plugin.apply_move(
                actor,
                name,
                arguments,
                source="bot",
                ctx=self.build_context(),
            )
            await self._record_move(actor, name, arguments, source="bot")
            await self._apply_actions(actions)
            if outcome := self.plugin.outcome():
                await self.finish(outcome)

    async def _apply_move(
        self,
        ctx: discord.Interaction,
        *,
        name: str,
        arguments: dict[str, Any],
        source: str,
        current_turn_required: bool,
    ) -> None:
        async with self._processing_move:
            actor = self._player_by_id(getattr(ctx.user, "id", None))
            if actor is None:
                await followup_send(ctx, get("move.no_active_game_description"), ephemeral=True)
                return
            current = self.plugin.current_turn()
            if current_turn_required and current is not None and current.id != actor.id:
                await followup_send(ctx, get("permissions.not_your_turn"), ephemeral=True)
                return
            actions = self.plugin.apply_move(
                actor,
                name,
                arguments,
                source=source,
                ctx=self.build_context(),
            )
            await self._record_move(actor, name, arguments, source=source)
            await self._apply_actions(actions)
            if outcome := self.plugin.outcome():
                await self.finish(outcome)
                return
        await self.run_bot_turn_if_needed()

    async def _record_move(
        self,
        actor: Any,
        name: str,
        arguments: dict[str, Any],
        *,
        source: str,
    ) -> None:
        try:
            next_number = db.database.get_move_count(self.game_id) + 1
            db.database.record_move(
                self.game_id,
                int(getattr(actor, "id", 0)) if not getattr(actor, "is_bot", False) else None,
                next_number,
                {"name": name, "arguments": arguments, "source": source},
                is_game_affecting=True,
                kind="system" if source == "bot" else "move",
            )
            actor_id = getattr(actor, "id", None)
            replay_event: dict[str, Any] = {
                "type": "move",
                "move_number": next_number,
                "command_name": name,
                "arguments": dict(arguments),
                "source": source,
            }
            if actor_id is not None:
                replay_event["user_id"] = int(actor_id)
            db.database.append_replay_event(self.game_id, replay_event)
        except Exception:
            self.logger.exception("Failed to record move match_id=%s", self.game_id)

    def _plugin_replay_hook(self, event_type: str, payload: dict[str, Any]) -> None:
        try:
            body: dict[str, Any] = {"type": event_type, **dict(payload)}
            db.database.append_replay_event(self.game_id, body)
        except Exception:
            self.logger.exception(
                "Failed to append plugin replay event match_id=%s type=%s",
                self.game_id,
                event_type,
            )

    async def _apply_actions(self, actions: tuple[Any, ...]) -> None:
        for action in actions:
            if isinstance(action, UpsertMessage):
                await self._upsert_message(action)
            elif isinstance(action, DeleteMessage):
                await self._delete_owned_message(action.key)

    async def _upsert_message(self, action: UpsertMessage) -> None:
        if action.target == "overview":
            view = self._build_overview_view(action.layout)
            if view is not None:
                await self._safe_edit_message(
                    self.status_message,
                    view=view,
                    attachments=[],
                )
            else:
                await self._safe_edit_message(
                    self.status_message,
                    content=action.layout.content,
                    attachments=[],
                )
            return
        if self.thread is None:
            return
        existing = self.owned_messages.get(action.key)
        view = self._build_view(action.layout)
        files = [
            discord.File(fp=asset_to_file(asset), filename=asset.filename)
            for asset in action.layout.attachments
        ]
        if existing is None:
            if view is None:
                message = await self.thread.send(
                    content=action.layout.content,
                    files=files or None,
                )
            else:
                send_kw: dict[str, Any] = {"view": view}
                if files:
                    send_kw["files"] = files
                message = await self.thread.send(**send_kw)
            self.owned_messages[action.key] = message
            self._record_owned_message(action.key, action.purpose, message, action.layout)
            return
        if view is None:
            await self._safe_edit_message(
                existing, content=action.layout.content, attachments=files
            )
        else:
            await self._safe_edit_message(existing, view=view, attachments=files)
        self._record_owned_message(action.key, action.purpose, existing, action.layout)

    async def _delete_owned_message(self, key: str) -> None:
        message = self.owned_messages.pop(key, None)
        if message is None:
            return
        try:
            await message.delete()
        except discord.HTTPException:
            self.logger.debug("Failed to delete owned message key=%s", key)
        if hasattr(db.database, "mark_bot_message_deleted"):
            try:
                db.database.mark_bot_message_deleted(message.id)
            except Exception:
                self.logger.debug(
                    "mark_bot_message_deleted failed for message_id=%s", message.id
                )

    async def _safe_edit_message(self, message: discord.Message | None, /, **kwargs) -> None:
        """Edit a message while handling Discord components-v2 content restrictions."""
        if message is None:
            return
        edit_kwargs = dict(kwargs)
        try:
            if (
                self._message_has_components_v2(message)
                and edit_kwargs.get("content") is not None
            ):
                self.logger.debug("Dropping content from edit because message uses components v2")
                edit_kwargs.pop("content", None)

            await message.edit(**edit_kwargs)
        except Exception as exc:
            if (
                edit_kwargs.get("content") is not None
                and self._is_http_exception(exc)
                and self._is_components_v2_content_error(exc)
            ):
                retry_kwargs = dict(edit_kwargs)
                retry_kwargs.pop("content", None)
                self.logger.debug("Retrying edit without content due to components v2 validation")
                try:
                    await message.edit(**retry_kwargs)
                    return
                except Exception:
                    self.logger.exception("Failed to edit message %s", getattr(message, "id", None))
                    return

            self.logger.exception("Failed to edit message %s", getattr(message, "id", None))

    @staticmethod
    def _is_http_exception(exc: Exception) -> bool:
        http_exception = getattr(discord, "HTTPException", None)
        return isinstance(http_exception, type) and isinstance(exc, http_exception)

    @staticmethod
    def _is_components_v2_content_error(exc: Exception) -> bool:
        text = str(exc)
        return "IS_COMPONENTS_V2" in text and "content" in text.lower()

    @staticmethod
    def _message_has_components_v2(message: discord.Message) -> bool:
        flags = getattr(message, "flags", None)
        if flags is None:
            return False

        marker = getattr(flags, "is_components_v2", None)
        if marker is not None:
            return bool(marker)

        flag_const = getattr(discord.MessageFlags, "IS_COMPONENTS_V2", None)
        if flag_const is None:
            return False
        flags_val = getattr(flags, "value", None)
        if flags_val is None:
            return False
        try:
            return (int(flags_val) & int(flag_const)) != 0
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _text_chunks_v2(text: str) -> list[str]:
        max_len = int(TEXT_DISPLAY_MAX)
        raw = (text or "").strip()
        if not raw:
            return []
        chunks: list[str] = []
        current = ""
        for line in raw.splitlines(keepends=True):
            if len(current) + len(line) > max_len and current:
                chunks.append(current.rstrip("\n"))
                current = line
            else:
                current += line
        if current:
            chunks.append(current.rstrip("\n"))
        return chunks or [raw[:max_len]]

    def _build_interactive_view(
        self,
        layout: MessageLayout,
        trailing_buttons: tuple[discord.ui.Button, ...] = (),
    ) -> RuntimeView | None:
        has_body = bool((layout.content or "").strip())
        has_game = bool(layout.buttons or layout.selects)
        has_trail = bool(trailing_buttons)
        if not has_body and not has_game and not has_trail:
            return None

        view = RuntimeView()
        container = discord.ui.Container()
        for chunk in self._text_chunks_v2(layout.content or ""):
            container.add_item(discord.ui.TextDisplay(chunk))
        if has_body and (has_game or has_trail):
            container.add_item(discord.ui.Separator())
        width = layout.button_row_width
        if width and width > 0 and layout.buttons:
            row_buttons: list[discord.ui.Button] = []
            for button in layout.buttons:
                row_buttons.append(self._make_button(button))
                if len(row_buttons) >= width:
                    ar = discord.ui.ActionRow()
                    for item in row_buttons:
                        ar.add_item(item)
                    container.add_item(ar)
                    row_buttons = []
            if row_buttons:
                ar = discord.ui.ActionRow()
                for item in row_buttons:
                    ar.add_item(item)
                container.add_item(ar)
        else:
            for button in layout.buttons:
                ar = discord.ui.ActionRow()
                ar.add_item(self._make_button(button))
                container.add_item(ar)
        for select in layout.selects:
            ar = discord.ui.ActionRow()
            ar.add_item(self._make_select(select))
            container.add_item(ar)
        if has_trail:
            if has_game:
                container.add_item(discord.ui.Separator())
            tr = discord.ui.ActionRow()
            for btn in trailing_buttons:
                tr.add_item(btn)
            container.add_item(tr)
        view.add_item(container)
        return view

    def _build_view(self, layout: MessageLayout) -> RuntimeView | None:
        return self._build_interactive_view(layout, ())

    def _build_overview_view(self, layout: MessageLayout) -> RuntimeView | None:
        if self.thread is None:
            return self._build_interactive_view(layout, ())
        trail = (
            discord.ui.Button(
                label="Spectate",
                style=discord.ButtonStyle.secondary,
                custom_id=f"{BUTTON_PREFIX_SPECTATE}{self.thread.id}",
            ),
            discord.ui.Button(
                label="Peek",
                style=discord.ButtonStyle.secondary,
                custom_id=f"{BUTTON_PREFIX_PEEK}{self.thread.id}",
            ),
        )
        return self._build_interactive_view(layout, trail)

    def _make_button(self, spec: ButtonSpec) -> discord.ui.Button:
        style_map = {
            "primary": discord.ButtonStyle.primary,
            "secondary": discord.ButtonStyle.secondary,
            "success": discord.ButtonStyle.success,
            "danger": discord.ButtonStyle.danger,
        }
        payload = urlencode(
            {
                "name": spec.action_name,
                "current_turn": "1" if spec.require_current_turn else "0",
                **{f"arg_{key}": str(value) for key, value in spec.arguments.items()},
            }
        )
        custom_id = CustomId(
            namespace="game",
            action="move",
            resource_id=self.thread.id if self.thread is not None else self.game_id,
            payload=payload,
        ).encode()
        # Discord requires a non-empty label for components. Some plugins may
        # provide only an emoji or an empty string. Use a zero-width space as
        # a safe placeholder so the component is valid while visually
        # appearing empty. Treat empty/whitespace-only labels as missing.
        label = spec.label if (spec.label and spec.label.strip()) else "\u200b"
        return discord.ui.Button(
            label=label,
            emoji=spec.emoji,
            style=style_map[spec.style],
            custom_id=custom_id,
            disabled=spec.disabled,
        )

    def _make_select(self, spec: SelectSpec) -> discord.ui.Select:
        payload = urlencode(
            {"name": spec.action_name, "current_turn": "1" if spec.require_current_turn else "0"}
        )
        custom_id = CustomId(
            namespace="game",
            action="select",
            resource_id=self.thread.id if self.thread is not None else self.game_id,
            payload=payload,
        ).encode()
        # Ensure each option has a non-empty label; fall back to the option
        # value if label is empty to satisfy Discord's API requirements.
        options = []
        for option in spec.options:
            opt_label = option.label if (option.label and option.label.strip()) else option.value
            options.append(discord.SelectOption(label=opt_label, value=option.value, default=option.default))

        select = discord.ui.Select(
            custom_id=custom_id,
            placeholder=spec.placeholder,
            options=options,
            disabled=spec.disabled,
        )
        return select

    def decode_component_payload(self, payload: str) -> tuple[str, dict[str, Any], bool]:
        parsed = parse_qs(payload)
        name = parsed.get("name", [""])[0]
        current_turn = parsed.get("current_turn", ["1"])[0] == "1"
        arguments = {
            key.removeprefix("arg_"): values[0]
            for key, values in parsed.items()
            if key.startswith("arg_")
        }
        return name, arguments, current_turn

    def _player_by_id(self, user_id: Any) -> Any | None:
        for player in self.players:
            if getattr(player, "id", None) == user_id:
                return player
        return None

    def _record_owned_message(
        self,
        key: str,
        purpose: str,
        message: discord.Message,
        layout: MessageLayout,
    ) -> None:
        if not hasattr(db.database, "upsert_bot_message"):
            return
        try:
            digest = hashlib.sha256((layout.content or "").encode("utf-8")).hexdigest()
            db.database.upsert_bot_message(
                match_id=self.game_id,
                discord_message_id=message.id,
                channel_id=message.channel.id,
                message_key=key,
                purpose=purpose,
                payload_digest=digest,
                metadata={"content_preview": (layout.content or "")[:500]},
            )
        except Exception:
            self.logger.debug("Failed to record owned message %s", key)


def asset_to_file(asset: BinaryAsset):
    from io import BytesIO

    fp = BytesIO(asset.data)
    fp.seek(0)
    return fp
