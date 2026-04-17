from __future__ import annotations

import io
from typing import Any

import discord

from api.Game import Game as BaseGame
from api.MessageComponents import Container, MediaGallery, Message, TextDisplay, format_data_table_image
from utils.containers import GameOverviewContainer
from utils.conversion import column_elo, column_turn
from utils.locale import fmt, get
from utils.views import SpectateView


def build_game_info_message(
        *,
        players: list[Any],
        game_type: str,
        turn_description: str,
        game_name: str,
        current_turn: Any,
) -> Message:
    info_table = format_data_table_image(
        {
            player: {
                "Rating": rating,
                "Turn": turn_marker,
            }
            for player, rating, turn_marker in zip(
            players,
            column_elo(players, game_type).split("\n"),
            column_turn(players, current_turn).split("\n"),
            strict=False,
        )
        }
    )
    return Message(
        Container(
            TextDisplay(f"## {fmt('game.state_title', game=game_name, players=len(players))}"),
            TextDisplay(turn_description),
            MediaGallery(info_table),
        )
    )


def build_game_status_view(
        *,
        game: Any,
        game_type: str,
        rated: bool,
        players: list[Any],
        current_turn: Any,
        thread_id: int,
        game_message_id: int,
        info_jump_url: str | None,
        peek_button_prefix: str,
        spectate_button_prefix: str,
) -> tuple[discord.ui.View, list[discord.File]]:
    overview = GameOverviewContainer(game.name, game_type, rated, players, current_turn)
    summary_bits: list[str] = []
    if overview.title:
        summary_bits.append(f"## {overview.title}")
    if overview.description:
        summary_bits.append(str(overview.description))
    summary_text = "\n\n".join(summary_bits).strip() or None
    overview_table = format_data_table_image(
        {
            player: {
                get("queue.field_rating"): rating,
                get("embeds.game_overview.field_turn"): turn_marker,
            }
            for player, rating, turn_marker in zip(
            players,
            column_elo(players, game_type).split("\n"),
            column_turn(players, current_turn).split("\n"),
            strict=False,
        )
        }
    )
    table_file = discord.File(io.BytesIO(overview_table), filename="game_overview.png")
    peek_button_id = None
    if type(game).player_state is not BaseGame.player_state:
        peek_button_id = f"{peek_button_prefix}{thread_id}/{game_message_id}"
    view = SpectateView(
        spectate_button_id=f"{spectate_button_prefix}{thread_id}",
        peek_button_id=peek_button_id,
        game_link=info_jump_url,
        summary_text=summary_text,
        table_image_url=f"attachment://{table_file.filename}",
    )
    return view, [table_file]
