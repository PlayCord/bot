"""Secret Hitler using the main/request Game API."""

from __future__ import annotations

import random
from collections import deque
from typing import TYPE_CHECKING, Any

from playcord.api import (
    BotDefinition,
    ButtonInput,
    CommandInput,
    GameContext,
    GameInput,
    GameMetadata,
    InputSource,
    InputSourceValue,
    InputTimeout,
    MessageLayout,
    Move,
    MoveParameter,
    Outcome,
    ParameterKind,
    Role,
    RoleAssignment,
    RoleFlow,
    RuntimeGame,
    SelectChoice,
    SelectInput,
    handler,
)
from playcord.api.plugin import register_game
from playcord.games._common import autocomplete_players, player_from_input

if TYPE_CHECKING:
    from playcord.core.player import Player

PHASE_NOMINATION = "nomination"
PHASE_VOTING = "voting"
PHASE_LEGISLATIVE = "legislative"
PHASE_POWER = "power"

STATE_ALIVE = "alive"
STATE_DEAD = "dead"

ROLE_LIBERAL = "liberal"
ROLE_FASCIST = "fascist"
ROLE_HITLER = "hitler"

POLICY_LIBERAL = "liberal"
POLICY_FASCIST = "fascist"

LIBERAL_POLICIES_TO_WIN = 5
FASCIST_POLICIES_TO_WIN = 6
FASCIST_POLICIES_FOR_HITLER_ELECTION = 3
MAX_REJECTIONS_BEFORE_TOPDECK = 3

LEGISLATIVE_TIMEOUT = 180
NOMINATION_TIMEOUT = 300
VOTE_TIMEOUT = 120
POWER_TIMEOUT = 240


class SecretHitlerGame(RuntimeGame):
    metadata = GameMetadata(
        key="secret_hitler",
        name="Secret Hitler",
        summary="A game of hidden identities, claims, and deception.",
        description=(
            "Liberals and Fascists compete to advance their agenda. "
            "One fascist is secretly Hitler."
        ),
        move_group_description="Secret Hitler commands",
        player_count=(5, 6, 7, 8, 9, 10),
        author="@playcord",
        version="2.0",
        author_link="https://github.com/PlayCord",
        source_link="https://github.com/PlayCord/bot/blob/main/playcord/games/secret_hitler.py",
        time="30min",
        difficulty="Hard",
        tags=("Social Deduction", "Hidden Identities", "Deception"),
        bots={
            "easy": BotDefinition(
                description="Random legal choices",
                callback=handler("bot_easy"),
            ),
            "hard": BotDefinition(
                description="Simple strategic legal choices",
                callback=handler("bot_hard"),
            ),
        },
        moves=(
            Move(
                name="nominate_chancellor",
                description="Nominate a Chancellor.",
                options=(
                    MoveParameter(
                        name="player_id",
                        description="Player to nominate as Chancellor",
                        kind=ParameterKind.string,
                        autocomplete=handler("autocomplete_nomination"),
                    ),
                ),
            ),
            Move(
                name="vote_government",
                description="Vote yes or no on the nominated government.",
                options=(
                    MoveParameter(
                        name="choice",
                        description="Your vote",
                        kind=ParameterKind.dropdown,
                        choices=(("Yes", "yes"), ("No", "no")),
                    ),
                ),
            ),
            Move(
                name="vote_policy",
                description="Discard a policy by type.",
                options=(
                    MoveParameter(
                        name="policy",
                        description="Policy to discard",
                        kind=ParameterKind.dropdown,
                        choices=(("Liberal", "liberal"), ("Fascist", "fascist")),
                    ),
                ),
            ),
            Move(
                name="investigate",
                description="Investigate another player.",
                options=(
                    MoveParameter(
                        name="player_id",
                        description="Player to investigate",
                        kind=ParameterKind.string,
                        autocomplete=handler("autocomplete_alive_players"),
                    ),
                ),
            ),
            Move(
                name="kill",
                description="Kill another player.",
                options=(
                    MoveParameter(
                        name="player_id",
                        description="Player to eliminate",
                        kind=ParameterKind.string,
                        autocomplete=handler("autocomplete_alive_players"),
                    ),
                ),
            ),
            Move(
                name="check_role",
                description="Check your role in the game.",
            ),
        ),
        role_flow=RoleFlow.random,
        peek_callback=handler("peek_status"),
    )

    def __init__(
        self,
        players: list[Player],
        *,
        match_options: dict[str, object] | None = None,
    ) -> None:
        super().__init__(players, match_options=match_options)
        self.phase = PHASE_NOMINATION
        self.liberal_policies = 0
        self.fascist_policies = 0
        self.player_order = list(players)
        random.shuffle(self.player_order)
        self.president_index = 0
        self.player_states = {int(player.id): STATE_ALIVE for player in players}
        self.government_votes: dict[int, bool] = {}
        self.nominated_chancellor: Player | None = None
        self.president: Player | None = None
        self.chancellor: Player | None = None
        self.government_history: deque[tuple[int, int]] = deque(maxlen=2)
        self.policy_deck = self._new_deck()
        self.policy_discard: list[str] = []
        self.government_rejects = 0
        self.roles: dict[int, str] = {}
        self.last_notice: str | None = None
        self.pending_power: str | None = None

    async def main(self) -> Outcome:
        self.roles = dict(self.context.roles)
        if not self.roles:
            self.roles = self._fallback_roles()
        while True:
            outcome = self._outcome()
            if outcome is not None:
                await self.update_message("board", self._layout(), purpose="board")
                return outcome
            self.president = self._current_president()
            self.chancellor = None
            self.nominated_chancellor = None
            self.phase = PHASE_NOMINATION
            nomination_outcome = await self._nomination_phase()
            if nomination_outcome is not None:
                return nomination_outcome
            outcome = self._outcome()
            if outcome is not None:
                await self.update_message("board", self._layout(), purpose="board")
                return outcome
            self.phase = PHASE_VOTING
            approved = await self._voting_phase()
            if not approved:
                self._reject_government()
                self._advance_president()
                continue
            if (
                self.fascist_policies >= FASCIST_POLICIES_FOR_HITLER_ELECTION
                and self.chancellor is not None
                and self._role(self.chancellor) == ROLE_HITLER
            ):
                return self._team_outcome(ROLE_FASCIST, "hitler elected chancellor")
            assert self.chancellor is not None
            self.government_history.append(
                (int(self.president.id), int(self.chancellor.id)),
            )
            self.government_rejects = 0
            self.phase = PHASE_LEGISLATIVE
            legislative_outcome = await self._legislative_phase()
            if legislative_outcome is not None:
                return legislative_outcome
            outcome = self._outcome()
            if outcome is not None:
                await self.update_message("board", self._layout(), purpose="board")
                return outcome
            power_outcome = await self._power_phase()
            if power_outcome is not None:
                return power_outcome
            self._advance_president()

    def get_roles(self) -> tuple[Role, ...]:
        return (
            Role(ROLE_LIBERAL, "Liberal"),
            Role(ROLE_FASCIST, "Fascist"),
            Role(ROLE_HITLER, "Hitler"),
        )

    def assign_roles(
        self,
        selections: dict[int, str] | None = None,
    ) -> list[RoleAssignment]:
        _ = selections
        players = list(self.players)
        random.shuffle(players)
        roles = self._role_pool(len(players))
        random.shuffle(roles)
        return [
            RoleAssignment(player_id=int(player.id), role_id=role, seat_index=index)
            for index, (player, role) in enumerate(zip(players, roles, strict=True))
        ]

    def match_global_summary(self, outcome: Outcome) -> str | None:
        if outcome.kind == "winner" and outcome.placements:
            winners = ", ".join(player.mention for player in outcome.placements[0])
            return f"Winners: {winners}"
        if outcome.kind == "interrupted":
            return "Interrupted"
        return None

    def match_summary(self, outcome: Outcome) -> dict[int, str] | None:
        if outcome.kind != "winner" or not outcome.placements:
            return {int(player.id): "Interrupted" for player in self.players}
        winners = {int(player.id) for player in outcome.placements[0]}
        return {
            int(player.id): ("Win" if int(player.id) in winners else "Loss")
            for player in self.players
        }

    def outcome_for_forfeit(
        self,
        players: Any,
        *,
        reason: str = "forfeit",
    ) -> Outcome:
        forfeited = {int(player.id) for player in players}
        if any(
            self._role(player) == ROLE_HITLER
            for player in self.players
            if int(player.id) in forfeited
        ):
            return self._team_outcome(ROLE_LIBERAL, reason)
        winners = [player for player in self.players if int(player.id) not in forfeited]
        losers = [player for player in self.players if int(player.id) in forfeited]
        return Outcome(kind="winner", placements=[winners, losers], reason=reason)

    async def _nomination_phase(self) -> Outcome | None:
        assert self.president is not None
        while self.chancellor is None:
            candidates = self._nomination_candidates(self.president)
            result = await self.request_input(
                [self.president],
                [
                    SelectInput(
                        id="nominate_select",
                        placeholder="Choose a Chancellor",
                        options=tuple(
                            SelectChoice(player.mention, str(player.id))
                            for player in candidates
                        ),
                    ),
                    CommandInput(
                        id="nominate_command",
                        command_name="nominate_chancellor",
                    ),
                ],
                timeout=NOMINATION_TIMEOUT,
                key="board",
                layout=self._layout(
                    extra=(f"{self.president.mention}, nominate a Chancellor."),
                ),
                purpose="board",
            )
            if isinstance(result, InputTimeout):
                return self.outcome_for_forfeit(
                    result.missing_players, reason="timeout"
                )
            if not isinstance(result, GameInput):
                continue
            nominee = self._player_from_input(result)
            if nominee is None or nominee not in candidates:
                self.last_notice = "Invalid Chancellor nomination."
                continue
            self.nominated_chancellor = nominee
            self.chancellor = nominee
            self.last_notice = f"{nominee.mention} was nominated for Chancellor."
            await self.record_move(
                result.actor,
                "nominate_chancellor",
                {"player_id": int(nominee.id)},
                source=result.source,
                input_id=result.input_id,
            )
        return None

    async def _voting_phase(self) -> bool:
        self.government_votes = {}
        assert self.president is not None
        assert self.chancellor is not None
        alive = self._alive_players()
        vote_inputs: tuple[ButtonInput | CommandInput, ...] = (
            ButtonInput(
                id="vote_yes",
                label="Yes",
                style="success",
                arguments={"choice": "yes"},
            ),
            ButtonInput(
                id="vote_no",
                label="No",
                style="danger",
                arguments={"choice": "no"},
            ),
            CommandInput(id="vote_command", command_name="vote_government"),
        )
        result = await self.request_input(
            alive,
            vote_inputs,
            timeout=VOTE_TIMEOUT,
            mode="all",
            on_timeout=lambda timeout: timeout,
            key="board",
            layout=self._layout(
                extra=(
                    f"Vote on President {self.president.mention} and "
                    f"Chancellor {self.chancellor.mention}."
                ),
            ),
            purpose="board",
        )
        responses = (
            list(result.responses.values())
            if isinstance(result, InputTimeout)
            else list(result)
            if isinstance(result, list)
            else []
        )
        for response in responses:
            vote = self._vote_from_input(response)
            self.government_votes[int(response.actor.id)] = vote
            await self.record_move(
                response.actor,
                "vote_government",
                {"choice": "yes" if vote else "no"},
                source=response.source,
                input_id=response.input_id,
            )
        for player in alive:
            self.government_votes.setdefault(int(player.id), False)
        yes = sum(1 for value in self.government_votes.values() if value)
        no = len(self.government_votes) - yes
        self.last_notice = f"Government vote: {yes} yes, {no} no."
        return yes > no

    async def _legislative_phase(self) -> Outcome | None:
        assert self.president is not None
        assert self.chancellor is not None
        self._reshuffle_if_needed()
        hand = [self.policy_deck.pop() for _ in range(3)]
        president_result = await self._request_policy_discard(
            self.president,
            hand,
            "president_discard",
            f"{self.president.mention}, discard one policy.",
        )
        if isinstance(president_result, InputTimeout):
            return self.outcome_for_forfeit(
                president_result.missing_players,
                reason="timeout",
            )
        president_discard, president_input = president_result
        await self.record_move(
            self.president,
            "vote_policy",
            {"policy": president_discard, "stage": "president"},
            source=president_input.source,
            input_id=president_input.input_id,
        )
        hand.remove(president_discard)
        self.policy_discard.append(president_discard)
        chancellor_result = await self._request_policy_discard(
            self.chancellor,
            hand,
            "chancellor_discard",
            f"{self.chancellor.mention}, discard one policy.",
        )
        if isinstance(chancellor_result, InputTimeout):
            return self.outcome_for_forfeit(
                chancellor_result.missing_players,
                reason="timeout",
            )
        chancellor_discard, chancellor_input = chancellor_result
        await self.record_move(
            self.chancellor,
            "vote_policy",
            {"policy": chancellor_discard, "stage": "chancellor"},
            source=chancellor_input.source,
            input_id=chancellor_input.input_id,
        )
        hand.remove(chancellor_discard)
        self.policy_discard.append(chancellor_discard)
        enacted = hand[0]
        if enacted == POLICY_LIBERAL:
            self.liberal_policies += 1
            self.pending_power = None
        else:
            self.fascist_policies += 1
            self.pending_power = self._power_for_fascist_count(self.fascist_policies)
        self.last_notice = f"A {enacted} policy was enacted."
        return None

    async def _request_policy_discard(
        self,
        actor: Player,
        hand: list[str],
        input_prefix: str,
        prompt: str,
    ) -> tuple[str, GameInput] | InputTimeout:
        while True:
            options = tuple(
                SelectChoice(
                    f"{policy.title()} policy #{index + 1}",
                    str(index),
                )
                for index, policy in enumerate(hand)
            )
            result = await self.request_input(
                [actor],
                [
                    SelectInput(
                        id=input_prefix,
                        placeholder="Discard a policy",
                        options=options,
                    ),
                    CommandInput(
                        id=f"{input_prefix}_command",
                        command_name="vote_policy",
                    ),
                ],
                timeout=LEGISLATIVE_TIMEOUT,
                key="board",
                layout=self._layout(extra=prompt),
                purpose="board",
                target="ephemeral",
            )
            if isinstance(result, InputTimeout):
                return result
            if not isinstance(result, GameInput):
                continue
            policy = self._policy_from_input(result, hand)
            if policy in hand:
                return policy, result
            self.last_notice = "Invalid policy choice."

    async def _power_phase(self) -> Outcome | None:
        power = self.pending_power
        self.pending_power = None
        if power is None:
            return None
        self.phase = PHASE_POWER
        if power == "policy_peek":
            assert self.president is not None
            peeked = ", ".join(self.policy_deck[-3:]) if self.policy_deck else "empty"
            await self.message_players(
                [self.president],
                f"You peeked at the top 3 policies: {peeked}",
            )
            self.last_notice = "The President peeked at the deck."
            return None
        if power == "investigate":
            target = await self._request_target(
                "investigate_target",
                "investigate",
                "Choose a player to investigate.",
            )
            if isinstance(target, InputTimeout):
                return self.outcome_for_forfeit(
                    target.missing_players, reason="timeout"
                )
            if target is not None:
                assert self.president is not None
                await self.message_players(
                    [self.president],
                    f"{target.mention} is on the {self._team_name(target)} team.",
                )
                self.last_notice = "The President investigated a player."
            return None
        if power == "kill":
            target = await self._request_target(
                "kill_target",
                "kill",
                "Choose a player to eliminate.",
            )
            if isinstance(target, InputTimeout):
                return self.outcome_for_forfeit(
                    target.missing_players, reason="timeout"
                )
            if target is None:
                return None
            assert self.president is not None
            self.player_states[int(target.id)] = STATE_DEAD
            await self.record_move(
                self.president,
                "kill",
                {"player_id": int(target.id)},
                source=InputSource.command,
                input_id="kill_target",
            )
            self.last_notice = f"{target.mention} was eliminated."
        return None

    async def _request_target(
        self,
        input_id: str,
        command_name: str,
        prompt: str,
    ) -> Player | InputTimeout | None:
        assert self.president is not None
        candidates = [
            player
            for player in self._alive_players()
            if int(player.id) != int(self.president.id)
        ]
        while candidates:
            result = await self.request_input(
                [self.president],
                [
                    SelectInput(
                        id=input_id,
                        placeholder="Choose a player",
                        options=tuple(
                            SelectChoice(player.mention, str(player.id))
                            for player in candidates
                        ),
                    ),
                    CommandInput(id=f"{input_id}_command", command_name=command_name),
                ],
                timeout=POWER_TIMEOUT,
                key="board",
                layout=self._layout(extra=prompt),
                purpose="board",
            )
            if isinstance(result, InputTimeout):
                return result
            if not isinstance(result, GameInput):
                continue
            target = self._player_from_input(result)
            if target in candidates:
                await self.record_move(
                    result.actor,
                    command_name,
                    {"player_id": int(target.id)},
                    source=result.source,
                    input_id=result.input_id,
                )
                return target
            self.last_notice = "Invalid target."
        return None

    def _reject_government(self) -> None:
        self.government_rejects += 1
        if self.government_rejects < MAX_REJECTIONS_BEFORE_TOPDECK:
            self.last_notice = (
                f"Government rejected. Rejection tracker: {self.government_rejects}/3."
            )
            return
        self._reshuffle_if_needed()
        enacted = self.policy_deck.pop()
        if enacted == POLICY_LIBERAL:
            self.liberal_policies += 1
            self.pending_power = None
        else:
            self.fascist_policies += 1
            self.pending_power = self._power_for_fascist_count(self.fascist_policies)
        self.government_rejects = 0
        self.last_notice = f"Chaos enacted a {enacted} policy."

    def _layout(self, *, extra: str | None = None) -> MessageLayout:
        lines = [
            "### Secret Hitler",
            f"Liberal policies: {self.liberal_policies}/{LIBERAL_POLICIES_TO_WIN}",
            f"Fascist policies: {self.fascist_policies}/{FASCIST_POLICIES_TO_WIN}",
            f"Phase: {self.phase}",
            f"President: {self.president.mention if self.president else 'TBD'}",
        ]
        if self.chancellor is not None:
            lines.append(f"Chancellor: {self.chancellor.mention}")
        alive = ", ".join(player.mention for player in self._alive_players())
        lines.append(f"Alive: {alive}")
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

    def autocomplete_nomination(
        self,
        actor: Player,
        current: str,
        *,
        ctx: GameContext,
    ) -> list[tuple[str, str]]:
        _ = ctx
        if self.president is None or int(actor.id) != int(self.president.id):
            return []
        return autocomplete_players(
            self._nomination_candidates(self.president),
            current,
        )

    def autocomplete_alive_players(
        self,
        actor: Player,
        current: str,
        *,
        ctx: GameContext,
    ) -> list[tuple[str, str]]:
        _ = actor
        _ = ctx
        return autocomplete_players(self._alive_players(), current)

    def bot_easy(
        self,
        player: Player,
        *,
        request: Any,
        ctx: GameContext,
    ) -> dict[str, object] | None:
        _ = ctx
        return self._bot_decision(player, request)

    def bot_hard(
        self,
        player: Player,
        *,
        request: Any,
        ctx: GameContext,
    ) -> dict[str, object] | None:
        _ = ctx
        role = self._role(player)
        input_ids = {spec.id for spec in request.inputs}
        if "vote_yes" in input_ids:
            if role != ROLE_LIBERAL:
                return {"input_id": "vote_yes"}
            return {"input_id": "vote_no"}
        return self._bot_decision(player, request)

    def _bot_decision(self, player: Player, request: Any) -> dict[str, object] | None:
        input_ids = {spec.id for spec in request.inputs}
        if "vote_yes" in input_ids:
            return {"input_id": random.choice(["vote_yes", "vote_no"])}
        if "nominate_select" in input_ids:
            candidates = self._nomination_candidates(player)
            if candidates:
                target = random.choice(candidates)
                return {
                    "input_id": "nominate_select",
                    "values": [str(target.id)],
                    "arguments": {"player_id": int(target.id)},
                }
        if "president_discard" in input_ids or "chancellor_discard" in input_ids:
            select_id = (
                "president_discard"
                if "president_discard" in input_ids
                else "chancellor_discard"
            )
            return {"input_id": select_id, "values": ["0"]}
        target_inputs = [item for item in input_ids if item.endswith("_target")]
        if target_inputs:
            candidates = [
                p for p in self._alive_players() if int(p.id) != int(player.id)
            ]
            if candidates:
                target = random.choice(candidates)
                return {
                    "input_id": target_inputs[0],
                    "values": [str(target.id)],
                    "arguments": {"player_id": int(target.id)},
                }
        return None

    def _outcome(self) -> Outcome | None:
        if self.liberal_policies >= LIBERAL_POLICIES_TO_WIN:
            return self._team_outcome(ROLE_LIBERAL, "liberal policies")
        if self.fascist_policies >= FASCIST_POLICIES_TO_WIN:
            return self._team_outcome(ROLE_FASCIST, "fascist policies")
        hitler = next(
            (player for player in self.players if self._role(player) == ROLE_HITLER),
            None,
        )
        if hitler is not None and self.player_states.get(int(hitler.id)) == STATE_DEAD:
            return self._team_outcome(ROLE_LIBERAL, "hitler eliminated")
        return None

    def _team_outcome(self, team: str, reason: str) -> Outcome:
        if team == ROLE_LIBERAL:
            winners = [p for p in self.players if self._role(p) == ROLE_LIBERAL]
            losers = [p for p in self.players if self._role(p) != ROLE_LIBERAL]
        else:
            winners = [p for p in self.players if self._role(p) != ROLE_LIBERAL]
            losers = [p for p in self.players if self._role(p) == ROLE_LIBERAL]
        return Outcome(kind="winner", placements=[winners, losers], reason=reason)

    def _current_president(self) -> Player:
        alive = self._alive_players()
        while self.player_order[self.president_index] not in alive:
            self.president_index = (self.president_index + 1) % len(self.player_order)
        return self.player_order[self.president_index]

    def _advance_president(self) -> None:
        while True:
            self.president_index = (self.president_index + 1) % len(self.player_order)
            if self.player_order[self.president_index] in self._alive_players():
                return

    def _alive_players(self) -> list[Player]:
        return [
            player
            for player in self.player_order
            if self.player_states.get(int(player.id)) == STATE_ALIVE
        ]

    def _nomination_candidates(self, president: Player) -> list[Player]:
        candidates = []
        previous = self.government_history[-1] if self.government_history else None
        previous_ids = set(previous) if previous else set()
        for player in self._alive_players():
            if int(player.id) == int(president.id):
                continue
            if len(self._alive_players()) > 5 and int(player.id) in previous_ids:
                continue
            candidates.append(player)
        return candidates

    def _role(self, player: Player) -> str:
        return self.roles.get(int(player.id), ROLE_LIBERAL)

    def _team_name(self, player: Player) -> str:
        return "fascist" if self._role(player) != ROLE_LIBERAL else "liberal"

    def _fallback_roles(self) -> dict[int, str]:
        roles = self._role_pool(len(self.players))
        return {
            int(player.id): role
            for player, role in zip(self.players, roles, strict=True)
        }

    @staticmethod
    def _role_pool(count: int) -> list[str]:
        fascists = 1 if count <= 6 else 2 if count <= 8 else 3
        liberals = count - fascists - 1
        return [ROLE_LIBERAL] * liberals + [ROLE_FASCIST] * fascists + [ROLE_HITLER]

    @staticmethod
    def _new_deck() -> list[str]:
        deck = [POLICY_LIBERAL] * 6 + [POLICY_FASCIST] * 11
        random.shuffle(deck)
        return deck

    def _reshuffle_if_needed(self) -> None:
        if len(self.policy_deck) >= 3:
            return
        self.policy_deck.extend(self.policy_discard)
        self.policy_discard = []
        random.shuffle(self.policy_deck)

    def _power_for_fascist_count(self, fascist_count: int) -> str | None:
        player_count = len(self.players)
        if fascist_count == 3 and player_count >= 7:
            return "investigate"
        if fascist_count == 4 and player_count <= 6:
            return "policy_peek"
        if fascist_count in {4, 5} and player_count >= 7:
            return "kill"
        if fascist_count == 5 and player_count <= 6:
            return "kill"
        return None

    def _player_from_input(self, result: GameInput) -> Player | None:
        return player_from_input(result, self.players)

    @staticmethod
    def _vote_from_input(result: GameInput) -> bool:
        if result.input_id == "vote_yes":
            return True
        if result.input_id == "vote_no":
            return False
        return str(result.arguments.get("choice", "")).lower() == "yes"

    async def record_move(
        self,
        actor: Player,
        name: str,
        arguments: dict[str, Any],
        *,
        source: InputSourceValue,
        input_id: str | None = None,
    ) -> None:
        if name == "check_role":
            role = self._role(actor)
            role_message = MessageLayout(content=f"Your role is: {role.title()}")
            await self.update_message(
                f"role_{actor.id}",
                role_message,
                target="ephemeral",
            )
        await super().record_move(
            actor,
            name,
            arguments,
            source=source,
            input_id=input_id,
        )

    @staticmethod
    def _policy_from_input(result: GameInput, hand: list[str]) -> str | None:
        if result.values:
            try:
                return hand[int(result.values[0])]
            except (IndexError, TypeError, ValueError):
                return None
        policy = str(result.arguments.get("policy", "")).lower()
        if policy in hand:
            return policy
        return None


register_game(SecretHitlerGame)
