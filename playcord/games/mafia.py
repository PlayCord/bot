"""Mafia using the runtime Game API."""

from __future__ import annotations

import random
from collections import Counter
from typing import TYPE_CHECKING

from playcord.api import (
    BotDefinition,
    ButtonInput,
    CommandInput,
    GameContext,
    GameInput,
    GameMetadata,
    InputTimeout,
    MessageLayout,
    Move,
    MoveParameter,
    Outcome,
    ParameterKind,
    Role,
    RoleAssignment,
    RoleFlow,
    RoleMode,
    RuntimeGame,
    SelectChoice,
    SelectInput,
    handler,
)
from playcord.api.match_options import MatchOptionSpec
from playcord.api.plugin import register_game
from playcord.games._common import autocomplete_players, player_from_input

if TYPE_CHECKING:
    from playcord.core.player import Player

ROLE_MAFIA = "mafia"
ROLE_DOCTOR = "doctor"
ROLE_VILLAGER = "villager"

PHASE_DAY_VOTE = "day_vote"
PHASE_NIGHT_MAFIA = "night_mafia"
PHASE_NIGHT_DOCTOR = "night_doctor"

INPUT_DAY_VOTE = "day_vote_select"
INPUT_NIGHT_ACTION = "night_action_select"
INPUT_MAFIA_CHAT = "mafia_chat_command"

SKIP_TOKEN = "skip"
MAX_STALEMATE_DAYS = 12

DAY_VOTE_TIMEOUT = 180
NIGHT_ACTION_TIMEOUT = 150
MAFIA_ONE_THRESHOLD = 6
MAFIA_TWO_THRESHOLD = 9
DOCTOR_MIN_PLAYERS = 5
RNG = random.SystemRandom()

_PHASE_LABELS = {
    PHASE_DAY_VOTE: "Day vote",
    PHASE_NIGHT_MAFIA: "Night (Mafia)",
    PHASE_NIGHT_DOCTOR: "Night",
}


class MafiaGame(RuntimeGame):
    """Runtime implementation of Mafia with day votes and night actions."""

    metadata = GameMetadata(
        key="mafia",
        name="Mafia",
        summary="A social deduction game of hidden roles and elimination.",
        description=(
            "Town tries to eliminate the mafia during the day while mafia eliminates "
            "town at night."
        ),
        move_group_description="Mafia commands",
        player_count=(5, 6, 7, 8, 9, 10, 11, 12),
        author="@playcord",
        version="2.0",
        author_link="https://github.com/PlayCord",
        source_link="https://github.com/PlayCord/bot/blob/main/playcord/games/mafia.py",
        time="15min",
        difficulty="Medium",
        tags=("Social Deduction", "Hidden Roles"),
        bots={
            "easy": BotDefinition(
                description="Picks a random legal target.",
                callback=handler("bot_easy"),
            ),
        },
        moves=(
            Move(
                name="day_vote",
                description="Vote to eliminate a player during the day.",
                options=(
                    MoveParameter(
                        name="player_id",
                        description="Player to vote for",
                        kind=ParameterKind.string,
                        autocomplete=handler("autocomplete_day_vote"),
                    ),
                ),
            ),
            Move(
                name="night_action",
                description="Submit your night action target.",
                options=(
                    MoveParameter(
                        name="player_id",
                        description="Player to target",
                        kind=ParameterKind.string,
                        autocomplete=handler("autocomplete_night_action"),
                    ),
                ),
            ),
            Move(
                name="mafia_chat",
                description="Send a private message to other mafia members.",
                options=(
                    MoveParameter(
                        name="message",
                        description="Message to send",
                        kind=ParameterKind.string,
                    ),
                ),
            ),
        ),
        role_mode=RoleMode.secret,
        role_flow=RoleFlow.random,
        player_roles=(ROLE_MAFIA, ROLE_DOCTOR, ROLE_VILLAGER),
        peek_callback=handler("peek_status"),
        customizable_options=(
            MatchOptionSpec(
                key="role_balance",
                label="Role balance",
                kind="preset",
                default="Standard",
                description=(
                    "Quick presets that set mafia and doctor counts together. "
                    "Fine-tune each role below if needed."
                ),
                presets=(
                    (
                        "Standard",
                        {"mafia_count": "auto", "doctor_count": "auto"},
                    ),
                    (
                        "Light (1 Mafia)",
                        {"mafia_count": "1", "doctor_count": "auto"},
                    ),
                    (
                        "Heavy (2 Mafia)",
                        {"mafia_count": "2", "doctor_count": "auto"},
                    ),
                    (
                        "Chaos (3 Mafia, no Doctor)",
                        {"mafia_count": "3", "doctor_count": "0"},
                    ),
                    (
                        "No Doctor",
                        {"mafia_count": "auto", "doctor_count": "0"},
                    ),
                ),
            ),
            MatchOptionSpec(
                key="mafia_count",
                label="Mafia count",
                kind="choices",
                default="auto",
                description=(
                    "How many mafia are in the game. Auto scales with player count "
                    "(1 at 5-6, 2 at 7-9, 3 at 10+)."
                ),
                choices=(
                    ("Auto (by player count)", "auto"),
                    ("1 Mafia", "1"),
                    ("2 Mafia", "2"),
                    ("3 Mafia", "3"),
                ),
            ),
            MatchOptionSpec(
                key="doctor_count",
                label="Doctor count",
                kind="choices",
                default="auto",
                description=(
                    "Whether a doctor can protect one player each night. "
                    "Auto adds a doctor when there are 5 or more players."
                ),
                choices=(
                    ("Auto (1 at 5+ players)", "auto"),
                    ("No Doctor", "0"),
                    ("1 Doctor", "1"),
                ),
            ),
        ),
    )

    def __init__(
        self,
        players: list[Player],
        *,
        match_options: dict[str, object] | None = None,
    ) -> None:
        super().__init__(players, match_options=match_options)
        self.day_number = 1
        self.phase = PHASE_DAY_VOTE
        self.alive: dict[int, bool] = {int(player.id): True for player in players}
        self.roles: dict[int, str] = {}
        self.last_notice: str | None = None
        self.days_without_elimination = 0

    async def main(self) -> Outcome:
        self.roles = dict(self.context.roles) or self._fallback_roles()
        await self._notify_roles()
        while True:
            outcome = self._outcome()
            if outcome is not None:
                await self.update_message("board", self._layout(), purpose="board")
                return outcome

            if self.days_without_elimination >= MAX_STALEMATE_DAYS:
                return Outcome.draw(
                    self._alive_players(),
                    reason="stalemate",
                )

            day_outcome = await self._day_phase()
            if day_outcome is not None:
                await self.update_message("board", self._layout(), purpose="board")
                return day_outcome

            outcome = self._outcome()
            if outcome is not None:
                await self.update_message("board", self._layout(), purpose="board")
                return outcome

            night_outcome = await self._night_phase()
            if night_outcome is not None:
                await self.update_message("board", self._layout(), purpose="board")
                return night_outcome

            self.day_number += 1

    async def _notify_roles(self) -> None:
        for player in self.players:
            role = self._role(player)
            await self.message_players(
                [player],
                f"**Mafia** — Your role: **{role.title()}**",
            )
        mafia = self._alive_players_for_role(ROLE_MAFIA)
        if len(mafia) > 1:
            teammates = ", ".join(
                player.mention
                for player in mafia
                if int(player.id) != int(mafia[0].id)
            )
            if teammates:
                for player in mafia:
                    await self.message_players(
                        [player],
                        f"Your mafia teammates: {teammates}",
                    )

    def get_roles(self) -> tuple[Role, ...]:
        return (
            Role(
                ROLE_MAFIA,
                "Mafia",
                "Eliminate townsfolk at night and reach parity with town.",
            ),
            Role(
                ROLE_DOCTOR,
                "Doctor",
                "Choose one player each night to protect from elimination.",
            ),
            Role(
                ROLE_VILLAGER,
                "Villager",
                "Use daytime votes to identify and eliminate the mafia.",
            ),
        )

    def assign_roles(
        self,
        selections: dict[int, str] | None = None,
    ) -> list[RoleAssignment]:
        _ = selections
        players = list(self.players)
        RNG.shuffle(players)
        role_pool = self._role_pool(len(players), self.match_options)
        RNG.shuffle(role_pool)
        return [
            RoleAssignment(player_id=int(player.id), role_id=role, seat_index=index)
            for index, (player, role) in enumerate(zip(players, role_pool, strict=True))
        ]

    @classmethod
    def validate_match_options(
        cls,
        player_count: int,
        match_options: dict[str, object] | None,
    ) -> bool | str:
        if player_count < 1:
            return "Invalid player count."
        mafia_count, doctor_count = cls._resolve_role_counts(
            player_count,
            match_options,
        )
        if mafia_count + doctor_count >= player_count:
            return (
                f"Too many special roles ({mafia_count} mafia, {doctor_count} doctor) "
                f"for {player_count} players."
            )
        return True

    def match_global_summary(self, outcome: Outcome) -> str | None:
        if outcome.kind == "winner" and outcome.placements:
            winners = ", ".join(player.mention for player in outcome.placements[0])
            return f"Winners: {winners}"
        if outcome.kind == "draw":
            return "Draw"
        if outcome.kind == "interrupted":
            return "Interrupted"
        return None

    def match_summary(self, outcome: Outcome) -> dict[int, str] | None:
        if outcome.kind == "draw":
            return {int(player.id): "Draw" for player in self.players}
        if outcome.kind != "winner" or not outcome.placements:
            return {int(player.id): "Interrupted" for player in self.players}
        winners = {int(player.id) for player in outcome.placements[0]}
        return {
            int(player.id): ("Win" if int(player.id) in winners else "Loss")
            for player in self.players
        }

    def autocomplete_day_vote(
        self,
        actor: Player,
        current: str,
        *,
        ctx: GameContext,
    ) -> list[tuple[str, str]]:
        _ = ctx
        if self.phase != PHASE_DAY_VOTE or not self._is_alive(actor):
            return []
        return autocomplete_players(
            self._alive_players(),
            current,
            extra=(("Skip vote", SKIP_TOKEN),),
        )

    def autocomplete_night_action(
        self,
        actor: Player,
        current: str,
        *,
        ctx: GameContext,
    ) -> list[tuple[str, str]]:
        _ = ctx
        if not self._is_alive(actor):
            return []
        role = self._role(actor)
        if self.phase == PHASE_NIGHT_MAFIA and role == ROLE_MAFIA:
            return autocomplete_players(
                [
                    player
                    for player_id in self._night_mafia_targets()
                    if (player := self.get_player(player_id)) is not None
                ],
                current,
            )
        if self.phase == PHASE_NIGHT_DOCTOR and role == ROLE_DOCTOR:
            return autocomplete_players(self._alive_players(), current)
        return []

    def bot_easy(
        self,
        player: Player,
        *,
        request: object,
        ctx: GameContext,
    ) -> dict[str, object] | None:
        _ = ctx
        if not self._is_alive(player):
            return None
        raw_inputs = getattr(request, "inputs", ())
        input_ids = {str(getattr(spec, "id", "")) for spec in raw_inputs}

        if INPUT_DAY_VOTE in input_ids and self.phase == PHASE_DAY_VOTE:
            candidates = [str(int(candidate.id)) for candidate in self._alive_players()]
            if not candidates:
                return None
            return {
                "input_id": INPUT_DAY_VOTE,
                "values": [RNG.choice(candidates)],
            }

        if INPUT_NIGHT_ACTION in input_ids:
            role = self._role(player)
            candidates: list[str] = []
            if self.phase == PHASE_NIGHT_MAFIA and role == ROLE_MAFIA:
                candidates = [str(pid) for pid in self._night_mafia_targets()]
            elif self.phase == PHASE_NIGHT_DOCTOR and role == ROLE_DOCTOR:
                candidates = [str(int(candidate.id)) for candidate in self._alive_players()]
            if candidates:
                return {
                    "input_id": INPUT_NIGHT_ACTION,
                    "values": [RNG.choice(candidates)],
                }
        return None

    async def handle_mafia_chat(self, game_input: GameInput) -> None:
        message_text = str(game_input.arguments.get("message", "") or "").strip()
        if not message_text:
            return
        if self._role(game_input.actor) != ROLE_MAFIA:
            return
        recipients = [
            player
            for player in self._alive_players_for_role(ROLE_MAFIA)
            if int(player.id) != int(game_input.actor.id)
        ]
        if recipients:
            await self.message_players(
                recipients,
                f"[Mafia] {game_input.actor.mention}: {message_text}",
            )
        await self.record_move(
            game_input.actor,
            "mafia_chat",
            {"message": message_text},
            source=game_input.source,
            input_id=game_input.input_id,
        )

    async def _day_phase(self) -> Outcome | None:
        self.phase = PHASE_DAY_VOTE
        alive_players = self._alive_players()
        vote_options = (
            *(SelectChoice(player.mention, str(player.id)) for player in alive_players),
            SelectChoice("Skip vote", SKIP_TOKEN),
        )

        result = await self.request_input(
            alive_players,
            [
                SelectInput(
                    id=INPUT_DAY_VOTE,
                    placeholder="Vote to eliminate",
                    options=vote_options,
                ),
                ButtonInput(
                    id="day_skip",
                    label="Skip",
                    arguments={"player_id": SKIP_TOKEN},
                ),
                CommandInput(id="day_vote_command", command_name="day_vote"),
            ],
            timeout=DAY_VOTE_TIMEOUT,
            mode="all",
            key="board",
            layout=self._layout(extra="Cast your day vote."),
            on_timeout=lambda timeout: timeout,
        )
        responses = self._collect_responses(result)
        if isinstance(result, InputTimeout) and not responses:
            return self.outcome_for_forfeit(result.missing_players, reason="timeout")

        votes: Counter[int] = Counter()
        skip_count = 0
        for response in responses:
            if self._skip_from_input(response):
                skip_count += 1
                await self.record_move(
                    response.actor,
                    "day_vote",
                    {"player_id": SKIP_TOKEN},
                    source=response.source,
                    input_id=response.input_id,
                )
                continue
            target = self._target_from_input(response)
            if target is None or not self._is_alive(target):
                continue
            votes[int(target.id)] += 1
            await self.record_move(
                response.actor,
                "day_vote",
                {"player_id": int(target.id)},
                source=response.source,
                input_id=response.input_id,
            )

        if not votes:
            self.days_without_elimination += 1
            if skip_count:
                self.last_notice = "Everyone skipped the vote. Nobody was eliminated."
            else:
                self.last_notice = "No valid votes were submitted."
            return None

        top_votes = max(votes.values())
        leaders = [player_id for player_id, count in votes.items() if count == top_votes]
        if len(leaders) != 1:
            self.days_without_elimination += 1
            self.last_notice = "The vote tied. Nobody was eliminated."
            return None

        eliminated = self.get_player(leaders[0])
        if eliminated is None:
            self.last_notice = "Day vote failed to resolve."
            return None
        self.alive[int(eliminated.id)] = False
        self.days_without_elimination = 0
        self.log_replay_event("eliminated", player_id=int(eliminated.id), phase="day")
        self.last_notice = f"{eliminated.mention} was eliminated by town vote."
        return None

    async def _night_phase(self) -> Outcome | None:
        mafia_players = self._alive_players_for_role(ROLE_MAFIA)
        if not mafia_players:
            return None

        self.phase = PHASE_NIGHT_MAFIA
        self.last_notice = "Night falls. Mafia are choosing a target."
        mafia_target, mafia_outcome = await self._collect_group_target(
            actors=mafia_players,
            allowed_ids=set(self._night_mafia_targets()),
            stage="mafia",
            include_mafia_chat=True,
        )
        if mafia_outcome is not None:
            return mafia_outcome

        doctor_players = self._alive_players_for_role(ROLE_DOCTOR)
        saved_target: int | None = None
        if doctor_players:
            self.phase = PHASE_NIGHT_DOCTOR
            saved_target, doctor_outcome = await self._collect_group_target(
                actors=doctor_players,
                allowed_ids={int(player.id) for player in self._alive_players()},
                stage="doctor",
                include_mafia_chat=False,
            )
            if doctor_outcome is not None:
                return doctor_outcome

        self._resolve_night_result(mafia_target=mafia_target, saved_target=saved_target)
        return None

    async def _collect_group_target(
        self,
        *,
        actors: list[Player],
        allowed_ids: set[int],
        stage: str,
        include_mafia_chat: bool,
    ) -> tuple[int | None, Outcome | None]:
        if not actors or not allowed_ids:
            return None, None

        target_players = [
            player
            for player_id in allowed_ids
            if (player := self.get_player(player_id)) is not None
        ]
        inputs: list[SelectInput | CommandInput | ButtonInput] = [
            SelectInput(
                id=INPUT_NIGHT_ACTION,
                placeholder="Choose a target",
                options=tuple(
                    SelectChoice(player.mention, str(player.id))
                    for player in target_players
                ),
            ),
            CommandInput(id="night_action_command", command_name="night_action"),
        ]
        if include_mafia_chat:
            inputs.append(
                CommandInput(
                    id=INPUT_MAFIA_CHAT,
                    command_name="mafia_chat",
                    argument_names=("message",),
                    handler=handler("handle_mafia_chat"),
                    counts_as_response=False,
                ),
            )

        result = await self.request_input(
            actors,
            inputs,
            timeout=NIGHT_ACTION_TIMEOUT,
            mode="all",
            key="board",
            layout=self._layout(),
            on_timeout=lambda timeout: timeout,
        )
        responses = self._collect_responses(result)
        if isinstance(result, InputTimeout) and not responses:
            return None, self.outcome_for_forfeit(
                result.missing_players,
                reason="timeout",
            )

        choices: Counter[int] = Counter()
        for response in responses:
            if response.input_id == INPUT_MAFIA_CHAT:
                continue
            target = self._target_from_input(response)
            if target is None:
                continue
            target_id = int(target.id)
            if target_id not in allowed_ids or not self._is_alive(target):
                continue
            choices[target_id] += 1
            await self.record_move(
                response.actor,
                "night_action",
                {"player_id": target_id, "stage": stage},
                source=response.source,
                input_id=response.input_id,
            )

        if not choices:
            return None, None

        top_votes = max(choices.values())
        leaders = [player_id for player_id, count in choices.items() if count == top_votes]
        return RNG.choice(leaders), None

    def _resolve_night_result(
        self,
        *,
        mafia_target: int | None,
        saved_target: int | None,
    ) -> None:
        if mafia_target is None:
            self.days_without_elimination += 1
            self.last_notice = "No one was eliminated overnight."
            return
        if saved_target is not None and mafia_target == saved_target:
            self.days_without_elimination += 1
            self.last_notice = "No one was eliminated overnight."
            return

        eliminated = self.get_player(mafia_target)
        if eliminated is None or not self._is_alive(eliminated):
            self.last_notice = "Night elimination failed to resolve."
            return

        self.alive[int(eliminated.id)] = False
        self.days_without_elimination = 0
        self.log_replay_event("eliminated", player_id=int(eliminated.id), phase="night")
        self.last_notice = f"At dawn, {eliminated.mention} was found eliminated."

    def _outcome(self) -> Outcome | None:
        alive_players = self._alive_players()
        mafia_alive = [
            player for player in alive_players if self._role(player) == ROLE_MAFIA
        ]
        town_alive = [
            player for player in alive_players if self._role(player) != ROLE_MAFIA
        ]

        if not mafia_alive:
            return self._team_outcome(ROLE_VILLAGER, "all mafia eliminated")
        if not town_alive or len(mafia_alive) >= len(town_alive):
            return self._team_outcome(ROLE_MAFIA, "mafia reached parity")
        return None

    def _team_outcome(self, winning_team: str, reason: str) -> Outcome:
        if winning_team == ROLE_MAFIA:
            winners = [
                player for player in self.players if self._role(player) == ROLE_MAFIA
            ]
            losers = [
                player for player in self.players if self._role(player) != ROLE_MAFIA
            ]
        else:
            winners = [
                player for player in self.players if self._role(player) != ROLE_MAFIA
            ]
            losers = [
                player for player in self.players if self._role(player) == ROLE_MAFIA
            ]
        return Outcome.win(winners=winners, losers=losers, reason=reason)

    def _layout(self, *, extra: str | None = None) -> MessageLayout:
        alive_mentions = ", ".join(player.mention for player in self._alive_players())
        dead_mentions = ", ".join(
            player.mention
            for player in self.players
            if not self.alive.get(int(player.id), False)
        )
        phase_label = _PHASE_LABELS.get(self.phase, "In progress")
        lines = [
            "### Mafia",
            f"Day {self.day_number} — {phase_label}",
            f"Alive: {alive_mentions or 'None'}",
        ]
        if dead_mentions:
            lines.append(f"Eliminated: {dead_mentions}")
        if self.last_notice:
            lines.append("")
            lines.append(self.last_notice)
        if extra:
            lines.append("")
            lines.append(extra)
        return MessageLayout(content="\n".join(lines))

    def peek_status(
        self,
        *,
        ctx: GameContext,
        actor: Player | None = None,
    ) -> str | None:
        _ = ctx
        if actor is None:
            return "Role info is unavailable."
        return f"Your role is: {self._role(actor).title()}"

    @staticmethod
    def _collect_responses(
        result: list[GameInput] | InputTimeout,
    ) -> list[GameInput]:
        if isinstance(result, InputTimeout):
            return list(result.responses.values())
        if isinstance(result, list):
            return list(result)
        return []

    def _alive_players(self) -> list[Player]:
        return [
            player for player in self.players if self.alive.get(int(player.id), False)
        ]

    def _alive_players_for_role(self, role: str) -> list[Player]:
        return [
            player for player in self._alive_players() if self._role(player) == role
        ]

    def _night_mafia_targets(self) -> list[int]:
        return [
            int(player.id)
            for player in self._alive_players()
            if self._role(player) != ROLE_MAFIA
        ]

    def _is_alive(self, player: Player) -> bool:
        return self.alive.get(int(player.id), False)

    def _role(self, player: Player) -> str:
        return self.roles.get(int(player.id), ROLE_VILLAGER)

    def _target_from_input(self, response: GameInput) -> Player | None:
        if response.input_id == "day_skip":
            return None
        return player_from_input(response, self.players)

    @staticmethod
    def _skip_from_input(response: GameInput) -> bool:
        raw = response.arguments.get("player_id")
        if raw is None and response.values:
            raw = response.values[0]
        return str(raw).strip().lower() == SKIP_TOKEN

    def _fallback_roles(self) -> dict[int, str]:
        assignments = self.assign_roles()
        return {assignment.player_id: assignment.role_id for assignment in assignments}

    @staticmethod
    def _auto_mafia_count(player_count: int) -> int:
        if player_count <= MAFIA_ONE_THRESHOLD:
            return 1
        if player_count <= MAFIA_TWO_THRESHOLD:
            return 2
        return 3

    @staticmethod
    def _auto_doctor_count(player_count: int) -> int:
        return 1 if player_count >= DOCTOR_MIN_PLAYERS else 0

    @classmethod
    def _resolve_role_counts(
        cls,
        player_count: int,
        match_options: dict[str, object] | None,
    ) -> tuple[int, int]:
        options = match_options or {}
        raw_mafia = options.get("mafia_count", "auto")
        raw_doctor = options.get("doctor_count", "auto")

        if str(raw_mafia) == "auto":
            mafia_count = cls._auto_mafia_count(player_count)
        else:
            mafia_count = int(raw_mafia)

        if str(raw_doctor) == "auto":
            doctor_count = cls._auto_doctor_count(player_count)
        else:
            doctor_count = int(raw_doctor)

        mafia_count = max(1, min(mafia_count, 3))
        doctor_count = max(0, min(doctor_count, 1))

        max_special = max(player_count - 1, 0)
        if mafia_count + doctor_count > max_special:
            doctor_count = min(doctor_count, max(0, max_special - mafia_count))
            mafia_count = min(mafia_count, max(1, max_special - doctor_count))

        return mafia_count, doctor_count

    @classmethod
    def _role_pool(
        cls,
        count: int,
        match_options: dict[str, object] | None = None,
    ) -> list[str]:
        mafia_count, doctor_count = cls._resolve_role_counts(count, match_options)
        villager_count = max(count - mafia_count - doctor_count, 0)
        return (
            [ROLE_MAFIA] * mafia_count
            + [ROLE_DOCTOR] * doctor_count
            + [ROLE_VILLAGER] * villager_count
        )


register_game(MafiaGame)
