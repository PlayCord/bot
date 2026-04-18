"""Typed rating helpers used across the domain and repositories."""

from __future__ import annotations

from dataclasses import dataclass

from playcord.domain.errors import ConfigurationError

DEFAULT_MU = 1000.0
DEFAULT_SIGMA_RATIO = 1 / 6
DEFAULT_TRUESKILL_PARAMETERS: dict[str, float] = {
    "sigma": DEFAULT_SIGMA_RATIO,
    "beta": 1 / 12,
    "tau": 1 / 100,
    "draw": 9 / 10,
}


@dataclass(frozen=True, slots=True)
class Rating:
    """A player's TrueSkill rating."""

    mu: float = DEFAULT_MU
    sigma: float = DEFAULT_MU * DEFAULT_SIGMA_RATIO

    @property
    def conservative(self) -> float:
        return self.mu - (3 * self.sigma)

    def display(self, *, uncertainty_threshold: float = 0.20) -> str:
        if self.sigma > uncertainty_threshold * self.mu:
            return f"{round(self.mu)}?"
        return str(round(self.mu))


def merge_trueskill_parameters(
    raw: dict[str, float] | None,
) -> dict[str, float]:
    """Return a complete, validated parameter set with defaults applied."""

    merged = dict(DEFAULT_TRUESKILL_PARAMETERS)
    if raw:
        merged.update(raw)

    required = {"sigma", "beta", "tau", "draw"}
    missing = required.difference(merged)
    if missing:
        missing_list = ", ".join(sorted(missing))
        raise ConfigurationError(
            f"Missing TrueSkill parameter(s): {missing_list}"
        )

    return {key: float(value) for key, value in merged.items()}
