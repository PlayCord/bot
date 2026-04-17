from __future__ import annotations

from collections import Counter
from typing import Any

import trueskill

from api.Game import RoleMode
from api.Player import Player
from configuration.constants import CURRENT_GAMES, CURRENT_MATCHMAKING, IN_GAME, IN_MATCHMAKING, LONG_SPACE_EMBED, MU
from utils import database as db
from utils.containers import GameOverContainer, container_send_kwargs, container_to_markdown
from utils.database import InternalPlayer
from utils.locale import get
from utils.logging_config import get_logger
from utils.trueskill_params import get_trueskill_parameters
from utils.views import RematchView


async def successful_matchmaking(interface: Any, game_interface_cls: type[Any]) -> None:
    """
    Callback called by MatchmakingInterface when the game is successfully started.
    Sets up and registers a new GameInterface-like object.
    """
    from api.exceptions import ContainerValidationError

    message = interface.message
    sm_log = get_logger("interfaces.successful_matchmaking")
    try:
        await _successful_matchmaking_impl(interface, game_interface_cls)
    except ContainerValidationError as e:
        sm_log.warning(
            "Container validation error during game setup (message_id=%s game_type=%s): %s",
            getattr(message, "id", None),
            getattr(interface, "game_type", None),
            str(e),
        )
        try:
            error_msg = (
                "❌ This game cannot be created right now. "
                "The game display has too many elements to fit in Discord's limits.\n\n"
                f"*Technical details: {str(e)[:100]}*"
            )
            await message.edit(
                content=error_msg,
                view=None,
                attachments=[],
            )
        except Exception:
            pass
    except Exception:
        sm_log.exception(
            "successful_matchmaking failed (message_id=%s game_type=%s)",
            getattr(message, "id", None),
            getattr(interface, "game_type", None),
        )
        try:
            await message.edit(
                content=get("system_error.internal_what_failed"),
                view=None,
                attachments=[],
            )
        except Exception:
            pass


async def _successful_matchmaking_impl(interface: Any, game_interface_cls: type[Any]) -> None:
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

    for p in list(players):
        IN_MATCHMAKING.pop(p, None)
    CURRENT_MATCHMAKING.pop(message.id, None)

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
    game = game_interface_cls(
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
        await game.setup()
        db.database.update_match_context(
            match_id=new_game_id,
            channel_id=message.channel.id,
            thread_id=game.thread.id,
        )
        CURRENT_GAMES.update({game.thread.id: game})
        await game.display_game_state()
    except Exception:
        _sm = get_logger("interfaces.successful_matchmaking")
        try:
            db.database.abandon_match(new_game_id, "interface_setup_failed")
        except Exception:
            _sm.exception(
                "abandon_match failed after setup error (match_id=%s message_id=%s game_type=%s)",
                new_game_id,
                getattr(message, "id", None),
                game_type,
            )
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


def pre_match_mu_sigma(player: Any, game_type: str) -> tuple[float, float]:
    stat = getattr(player, game_type, None)
    if stat is not None and hasattr(stat, "mu"):
        return float(stat.mu), float(stat.sigma)
    if isinstance(player, Player):
        return float(player.mu), float(player.sigma)
    raise TypeError(
        f"Cannot read pre-match rating for {type(player).__name__!r} (game_type={game_type!r})"
    )


async def rating_groups_to_string(
        rankings: list[int],
        groups: list[dict[Any, trueskill.Rating]],
        game_type: str,
) -> tuple[str, dict[int, dict[str, str | bool | int | Any]]]:
    player_ratings = {}
    current_place = 1
    nums_current_place = 0
    matching = 0

    keys = [next(iter(p)) for p in groups]
    all_ratings = {list(p.keys())[0]: list(p.values())[0] for p in groups}
    rank_tie_counts = Counter(rankings)

    for i, pre_rated_player in enumerate(keys):
        if rankings[i] == matching:
            nums_current_place += 1
        else:
            current_place += nums_current_place
            matching = rankings[i]
            nums_current_place = 1

        starting_mu, starting_sigma = pre_match_mu_sigma(pre_rated_player, game_type)
        aftermath_mu, aftermath_sigma = all_ratings[pre_rated_player].mu, all_ratings[pre_rated_player].sigma
        mu_delta = str(round(aftermath_mu - starting_mu))
        if not mu_delta.startswith("-"):
            mu_delta = "+" + mu_delta

        player_ratings.update({
            pre_rated_player.id: {
                "old_mu": round(starting_mu),
                "delta": mu_delta,
                "place": current_place,
                "tied": rank_tie_counts[rankings[i]] > 1,
                "new_mu": aftermath_mu,
                "old_sigma": starting_sigma,
                "new_sigma": aftermath_sigma,
            }
        })

    player_string = "\n".join([
        f"{player_ratings[p]['place']}{'T' if player_ratings[p]['tied'] else ''}."
        f"{LONG_SPACE_EMBED}<@{p}>{LONG_SPACE_EMBED}{player_ratings[p]['old_mu']}"
        f"{LONG_SPACE_EMBED}({player_ratings[p]['delta']})"
        for p in player_ratings
    ])
    return player_string, player_ratings


async def non_rated_groups_to_string(rankings: list[int], groups: list[InternalPlayer]) -> str:
    player_ratings = []
    current_place = 1
    nums_current_place = 0
    matching = 0
    rank_tie_counts = Counter(rankings)

    for i, pre_rated_player in enumerate(groups):
        if rankings[i] == matching:
            nums_current_place += 1
        else:
            current_place += nums_current_place
            matching = rankings[i]
            nums_current_place = 1

        show_tied = "T" if rank_tie_counts[rankings[i]] > 1 else ""
        player_ratings.append(f"{current_place}{show_tied}.{LONG_SPACE_EMBED}{pre_rated_player.mention}")
    return "\n".join(player_ratings)


async def game_over(
        interface: Any,
        outcome: str | Player | InternalPlayer | list[list[InternalPlayer | Player]],
) -> None:
    interface.ending_game = True
    game_type = interface.game_type
    thread = interface.thread
    outbound_message = interface.status_message
    rated = interface.rated
    players = interface.players
    game_id = interface.game_id

    ts = get_trueskill_parameters(game_type)
    environment = trueskill.TrueSkill(
        mu=MU,
        sigma=MU * ts["sigma"],
        beta=MU * ts["beta"],
        tau=MU * ts["tau"],
        draw_probability=ts["draw"],
        backend="mpmath",
    )

    if isinstance(outcome, str):
        error_text = f"{get('game.error_during_move')} {str(outcome).strip()}".strip()
        await outbound_message.edit(content=error_text, view=None, attachments=[])
        await interface.await_pending_ui_tasks()
        await thread.edit(locked=True, archived=True, reason=get("threads.game_crashed"))
        await thread.send(error_text)
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
        if isinstance(outcome, (Player, InternalPlayer)):
            winner_mu, winner_sigma = pre_match_mu_sigma(outcome, game_type)
            winner = environment.create_rating(winner_mu, winner_sigma)
            losers = [
                {p: environment.create_rating(*pre_match_mu_sigma(p, game_type))}
                for p in players
                if p.id != outcome.id
            ]
            rating_groups = [{outcome: winner}, *losers]
            rankings = [0, *[1 for _ in range(len(players) - 1)]]
        else:
            current_ranking = 0
            rankings = []
            rating_groups = []
            for placement in outcome:
                for player in placement:
                    rankings.append(current_ranking)
                    rating_groups.append({player: environment.create_rating(player.mu, player.sigma)})
                current_ranking += 1

        if interface.forfeited_player_ids:
            player_order = []
            for group in rating_groups:
                for player in group:
                    player_order.append(player)
            if rankings:
                max_ranking = max(rankings)
                for i, player_obj in enumerate(player_order):
                    if getattr(player_obj, "id", None) in interface.forfeited_player_ids:
                        rankings[i] = max_ranking + 1

        adjusted_rating_groups = environment.rate(rating_groups=rating_groups, ranks=rankings)
        player_string, player_ratings = await rating_groups_to_string(rankings, adjusted_rating_groups, game_type)
        get_logger("interfaces.ratings").debug(
            "rated game_over: game_id=%s game_type=%s rankings=%s player_ratings_keys=%s",
            game_id,
            game_type,
            rankings,
            list(player_ratings) if player_ratings else None,
        )
        player_ids_in_order = list(player_ratings)
        ranking_display = {pid: rankings[i] + 1 for i, pid in enumerate(player_ids_in_order)}
        ratings = {}
        for player in player_ratings:
            data = player_ratings[player]
            new_mu = data["new_mu"]
            new_sigma = data["new_sigma"]
            ratings.update({
                player: {
                    "uid": player,
                    "new_mu": new_mu,
                    "new_sigma": new_sigma,
                    "mu_delta": new_mu - data["old_mu"],
                    "sigma_delta": new_sigma - data["old_sigma"],
                    "ranking": data.get("ranking", ranking_display[player]),
                }
            })

        db.database.end_game(match_id=game_id, game_name=game_type, rating_updates=ratings, final_scores=None)
    else:
        rankings = []
        groups = []
        if isinstance(outcome, (Player, InternalPlayer)):
            groups = [outcome, *[p for p in players if p.id != outcome.id]]
            rankings = [0, *[1 for _ in range(len(players) - 1)]]
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

    if interface.forfeited_player_ids:
        outcome_summaries = dict(outcome_summaries or {})
        for player in players:
            if player.id in interface.forfeited_player_ids:
                outcome_summaries[player.id] = get("forfeit.summary")

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
                "has_outcome_summary": outcome_summaries is not None or outcome_global_summary is not None,
            },
        )
    except Exception:
        pass

    for p in players:
        IN_GAME.pop(p, None)
    CURRENT_GAMES.pop(thread.id)
    replay_id = getattr(interface, "match_public_code", None) or str(game_id)

    game_over_container = GameOverContainer(
        rankings=player_string,
        game_name=interface.game.name,
        players=players,
        outcome_summaries=outcome_summaries,
        outcome_global_summary=outcome_global_summary,
        replay_id=replay_id,
        forfeited_player_ids=interface.forfeited_player_ids if interface.forfeited_player_ids else None,
    )

    await thread.send(**container_send_kwargs(game_over_container))
    await outbound_message.edit(view=RematchView(game_id, summary_text=container_to_markdown(game_over_container)))
    await interface.await_pending_ui_tasks()
    await thread.edit(locked=True, archived=True, reason=get("threads.game_over"))
