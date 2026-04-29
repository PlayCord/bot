"""Rating service and TrueSkill match outcome calculations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import trueskill

from playcord.api.trueskill_config import get_trueskill_parameters
from playcord.core.rating import DEFAULT_MU, STARTING_RATING

if TYPE_CHECKING:
    from playcord.infrastructure.database import PlayerRepository


@dataclass(slots=True)
class RatingService:
    repository: PlayerRepository

    def get_for_user(self, user_id: int) -> Any | None:
        return self.repository.get(user_id)


def player_mu_sigma(player: Any, game_type: str) -> tuple[float, float]:
    """Resolve mu/sigma from a plugin player object for ``game_type``."""
    mu = getattr(player, "mu", None)
    sigma = getattr(player, "sigma", None)
    if mu is not None and sigma is not None:
        return float(mu), float(sigma)

    game_rating = getattr(player, game_type, None)
    game_mu = getattr(game_rating, "mu", None)
    game_sigma = getattr(game_rating, "sigma", None)
    if game_mu is not None and game_sigma is not None:
        return float(game_mu), float(game_sigma)

    msg = f"Player {player!r} does not expose rating for game_type={game_type!r}"
    raise AttributeError(
        msg,
    )


def rated_results_for_placements(
    players: list[Any],
    game_type: str,
    placements: list[list[Any]],
) -> dict[int, dict[str, Any]]:
    """Compute post-match rating rows for a rated game."""
    ts = get_trueskill_parameters(game_type)
    environment = trueskill.TrueSkill(
        mu=DEFAULT_MU,
        sigma=STARTING_RATING * ts["sigma"],
        beta=STARTING_RATING * ts["beta"],
        tau=STARTING_RATING * ts["tau"],
        draw_probability=ts["draw"],
        backend="mpmath",
    )
    ranking_by_id: dict[int, int] = {}
    for rank_index, group in enumerate(placements):
        for player in group:
            ranking_by_id[int(player.id)] = rank_index
    player_ratings = [player_mu_sigma(player, game_type) for player in players]
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


def unrated_results_for_placements(
    players: list[Any],
    game_type: str,
    placements: list[list[Any]],
) -> dict[int, dict[str, Any]]:
    """Build neutral rating rows for an unrated game."""
    ranking_by_id: dict[int, int] = {}
    for rank_index, group in enumerate(placements):
        for player in group:
            ranking_by_id[int(player.id)] = rank_index + 1
    results: dict[int, dict[str, Any]] = {}
    for player in players:
        mu_before, sigma_before = player_mu_sigma(player, game_type)
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
