"""Match start/finish orchestration for GameRuntime."""

from __future__ import annotations

from typing import Any

import trueskill

from playcord import state as session_state
from playcord.application.services.game_runtime import GameRuntime
from playcord.infrastructure.app_constants import MU
from playcord.utils import database as db
from playcord.utils.locale import get
from playcord.utils.logging_config import get_logger
from playcord.utils.trueskill_params import get_trueskill_parameters
from playcord.utils.views import RematchView

CURRENT_MATCHMAKING = session_state.CURRENT_MATCHMAKING
IN_GAME = session_state.IN_GAME
IN_MATCHMAKING = session_state.IN_MATCHMAKING

log = get_logger("match.lifecycle")


async def start_match_from_lobby(
    interface: Any, plugin_class: type[Any]
) -> GameRuntime:
    message = interface.message
    players = (
        interface.all_players()
        if callable(getattr(interface, "all_players", None))
        else list(interface.queued_players)
    )
    has_bots = any(getattr(player, "is_bot", False) for player in players)
    for player in list(interface.queued_players):
        IN_MATCHMAKING.pop(player, None)
        player_id = getattr(player, "id", None)
        if player_id is not None:
            IN_MATCHMAKING.pop(int(player_id), None)
    CURRENT_MATCHMAKING.pop(message.id, None)

    match_options = dict(getattr(interface, "match_settings", {}) or {})
    match_id, match_code = db.database.create_game(
        game_name=interface.game_type,
        guild_id=message.guild.id,
        participants=[player.id for player in players],
        is_rated=bool(interface.rated and not has_bots),
        channel_id=message.channel.id,
        game_config={"match_options": match_options},
    )
    runtime = GameRuntime(
        game_type=interface.game_type,
        plugin_class=plugin_class,
        overview_message=message,
        creator=interface.creator,
        players=players,
        rated=bool(interface.rated and not has_bots),
        match_id=match_id,
        match_public_code=match_code,
        match_options=match_options,
    )
    await runtime.setup()
    db.database.update_match_context(
        match_id=match_id,
        channel_id=message.channel.id,
        thread_id=runtime.thread.id if runtime.thread is not None else None,
    )
    return runtime


async def finish_match(runtime: GameRuntime, outcome: Any) -> None:
    placements = getattr(outcome, "placements", []) or []
    players = list(runtime.players)
    if runtime.rated:
        results = _rated_results(players, runtime.game_type, placements)
    else:
        results = _unrated_results(players, runtime.game_type, placements)

    final_state = {
        "outcome": getattr(outcome, "kind", "winner"),
        "reason": getattr(outcome, "reason", None),
        "placements": [
            [getattr(player, "id", None) for player in group] for group in placements
        ],
    }
    db.database.end_match(runtime.game_id, final_state, results)

    global_summary: str | None = None
    summaries: dict[int, str] | None = None
    mg = getattr(runtime.plugin, "match_global_summary", None)
    if callable(mg):
        try:
            global_summary = mg(outcome)
        except Exception:
            log.exception("match_global_summary failed match_id=%s", runtime.game_id)
    ms = getattr(runtime.plugin, "match_summary", None)
    if callable(ms):
        try:
            raw = ms(outcome)
        except Exception:
            log.exception("match_summary failed match_id=%s", runtime.game_id)
            raw = None
        if isinstance(raw, dict) and raw:
            summaries = {}
            for key, text in raw.items():
                try:
                    uid = int(key)
                except (TypeError, ValueError):
                    continue
                summaries[uid] = str(text)

    if (global_summary and str(global_summary).strip()) or summaries:
        try:
            db.database.merge_match_metadata_outcome_display(
                runtime.game_id,
                summaries=summaries,
                global_summary=global_summary,
            )
        except Exception:
            log.exception(
                "merge_match_metadata_outcome_display failed match_id=%s",
                runtime.game_id,
            )

    for player in players:
        player_id = getattr(player, "id", None)
        if player_id is not None:
            IN_GAME.pop(int(player_id), None)
    if runtime.thread is not None:
        session_state.CURRENT_GAMES.pop(runtime.thread.id, None)

    summary = _summary_text(runtime, outcome, results)
    if runtime.thread is not None:
        await runtime.thread.send(summary)
        await runtime.thread.edit(
            locked=True, archived=True, reason=get("threads.game_over")
        )
    rematch_view = RematchView(runtime.game_id, summary_text=summary)
    safe_edit = getattr(runtime, "_safe_edit_message", None)
    if callable(safe_edit):
        await safe_edit(
            runtime.status_message,
            content=summary,
            view=rematch_view,
            attachments=[],
        )
    else:
        await runtime.status_message.edit(
            content=summary,
            view=rematch_view,
            attachments=[],
        )


def _rated_results(
    players: list[Any], game_type: str, placements: list[list[Any]]
) -> dict[int, dict[str, Any]]:
    ts = get_trueskill_parameters(game_type)
    environment = trueskill.TrueSkill(
        mu=MU,
        sigma=MU * ts["sigma"],
        beta=MU * ts["beta"],
        tau=MU * ts["tau"],
        draw_probability=ts["draw"],
        backend="mpmath",
    )
    ranking_by_id: dict[int, int] = {}
    for rank_index, group in enumerate(placements):
        for player in group:
            ranking_by_id[int(player.id)] = rank_index
    player_ratings = [_player_rating(player, game_type) for player in players]
    rating_groups = [
        {player: environment.create_rating(mu, sigma)}
        for player, (mu, sigma) in zip(players, player_ratings, strict=False)
    ]
    ranks = [ranking_by_id.get(int(player.id), len(players)) for player in players]
    adjusted = environment.rate(rating_groups=rating_groups, ranks=ranks)
    results: dict[int, dict[str, Any]] = {}
    for index, player in enumerate(players):
        mu_before, sigma_before = player_ratings[index]
        rating = adjusted[index][player]
        results[int(player.id)] = {
            "ranking": ranks[index] + 1,
            "score": None,
            "mu_before": mu_before,
            "sigma_before": sigma_before,
            "new_mu": float(rating.mu),
            "new_sigma": float(rating.sigma),
            "mu_delta": float(rating.mu - mu_before),
            "sigma_delta": float(rating.sigma - sigma_before),
        }
    return results


def _unrated_results(
    players: list[Any], game_type: str, placements: list[list[Any]]
) -> dict[int, dict[str, Any]]:
    ranking_by_id: dict[int, int] = {}
    for rank_index, group in enumerate(placements):
        for player in group:
            ranking_by_id[int(player.id)] = rank_index + 1
    results: dict[int, dict[str, Any]] = {}
    for player in players:
        mu_before, sigma_before = _player_rating(player, game_type)
        results[int(player.id)] = {
            "ranking": ranking_by_id.get(int(player.id), len(players)),
            "score": None,
            "mu_before": mu_before,
            "sigma_before": sigma_before,
            "new_mu": mu_before,
            "new_sigma": sigma_before,
            "mu_delta": 0.0,
            "sigma_delta": 0.0,
        }
    return results


def _player_rating(player: Any, game_type: str) -> tuple[float, float]:
    mu = getattr(player, "mu", None)
    sigma = getattr(player, "sigma", None)
    if mu is not None and sigma is not None:
        return float(mu), float(sigma)

    game_rating = getattr(player, game_type, None)
    game_mu = getattr(game_rating, "mu", None)
    game_sigma = getattr(game_rating, "sigma", None)
    if game_mu is not None and game_sigma is not None:
        return float(game_mu), float(game_sigma)

    raise AttributeError(
        f"Player {player!r} does not expose rating for game_type={game_type!r}"
    )


def _summary_text(
    runtime: GameRuntime, outcome: Any, results: dict[int, dict[str, Any]]
) -> str:
    lines = [f"**{runtime.plugin.metadata.name}** finished."]
    if getattr(outcome, "kind", None) == "winner" and getattr(
        outcome, "placements", None
    ):
        winner = outcome.placements[0][0]
        lines.append(f"Winner: {winner.mention}")
    elif getattr(outcome, "kind", None) == "draw":
        lines.append("Result: Draw")
    if runtime.rated:
        lines.append("")
        for player in runtime.players:
            result = results[int(player.id)]
            delta = round(result["mu_delta"])
            delta_text = f"{delta:+d}"
            lines.append(
                f"{player.mention}: {round(result['mu_before'])} ({delta_text})"
            )
    return "\n".join(lines)
