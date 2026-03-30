from api.Arguments import Integer
from api.Command import Command
from api.Game import Game, PlayerOrder
from api.MessageComponents import DataTable, Description
from api.Player import Player
from api.Response import Response


class MastermindDuelGame(Game):
    begin_command_description = "Breaker guesses a secret code set by the setter."
    move_command_group_description = "Commands for Mastermind Duel"
    description = "Player 1 sets a 4-digit secret code (1-6). Player 2 has 10 guesses to crack it."
    name = "Mastermind Duel"
    players = 2
    player_order = PlayerOrder.PRESERVE
    moves = [
        Command(
            name="code",
            description="Set or guess the 4-digit code (digits 1-6).",
            options=[Integer(argument_name="code", description="4-digit code like 1234", min_value=1111, max_value=6666)],
            callback="submit_code",
        )
    ]
    author = "@copilot"
    version = "1.0"
    author_link = "https://github.com/github"
    source_link = "https://github.com/PlayCord/bot/blob/main/games/MastermindDuel.py"
    time = "6min"
    difficulty = "Medium"

    def __init__(self, players: list[Player]) -> None:
        self.players = players
        self.setter = players[0]
        self.breaker = players[1]
        self.turn = 0
        self.phase = "set_code"
        self.secret: list[int] | None = None
        self.attempts = 0
        self.max_attempts = 10
        self.history: list[tuple[str, str]] = []
        self.winner: Player | None = None
        self.last_action = f"{self.setter.mention} must set the code."

    def state(self):
        if self.winner:
            status = f"🏁 Winner: {self.winner.mention}"
        elif self.phase == "set_code":
            status = f"🔒 Waiting for {self.setter.mention} to set code."
        else:
            status = f"➡️ Turn: {self.breaker.mention} ({self.attempts}/{self.max_attempts} guesses used)"

        rendered_history = "\n".join([f"{g} → {f}" for g, f in self.history[-8:]]) if self.history else "No guesses yet."
        description = f"{status}\n\n{self.last_action}\n\n**History**\n{rendered_history}"
        table = DataTable(
            {
                self.setter: {"Role:": "Setter"},
                self.breaker: {"Role:": "Breaker"},
            }
        )
        return [Description(description), table]

    def current_turn(self) -> Player:
        if self.phase == "set_code":
            return self.setter
        return self.breaker

    def submit_code(self, player: Player, code: int):
        if self.phase == "set_code":
            return self._set_code(player, code)
        return self._guess(player, code)

    def _set_code(self, player: Player, code: int):
        if self.phase != "set_code":
            return Response(content="Code is already set.", ephemeral=True, delete_after=5)

        digits = self._parse_code(code)
        if digits is None:
            return Response(content="Code must be exactly 4 digits, each between 1 and 6.", ephemeral=True, delete_after=8)

        self.secret = digits
        self.phase = "guessing"
        self.turn = 1
        self.last_action = f"{player.mention} set a secret code. {self.breaker.mention} may now guess."
        return Response(content="Your secret code has been set.", ephemeral=True, delete_after=6)

    def _guess(self, player: Player, code: int):
        if self.phase != "guessing" or self.secret is None:
            return Response(content="Code has not been set yet.", ephemeral=True, delete_after=5)

        digits = self._parse_code(code)
        if digits is None:
            return Response(content="Guess must be exactly 4 digits, each between 1 and 6.", ephemeral=True, delete_after=8)

        self.attempts += 1
        exact, partial = self._score_guess(digits, self.secret)
        guess_string = "".join(str(d) for d in digits)
        feedback = f"{exact} exact, {partial} partial"
        self.history.append((guess_string, feedback))
        self.last_action = f"{player.mention} guessed `{guess_string}`: {feedback}."

        if exact == 4:
            self.winner = self.breaker
            return None
        if self.attempts >= self.max_attempts:
            self.winner = self.setter
            reveal = "".join(str(d) for d in self.secret)
            self.last_action += f" Secret was `{reveal}`."
            return None

        return Response(content=f"Feedback: {feedback}", ephemeral=True, delete_after=8)

    def outcome(self):
        if self.winner:
            return self.winner
        return None

    def _parse_code(self, code: int) -> list[int] | None:
        digits = [int(x) for x in str(code)]
        if len(digits) != 4:
            return None
        if any(d < 1 or d > 6 for d in digits):
            return None
        return digits

    def _score_guess(self, guess: list[int], secret: list[int]) -> tuple[int, int]:
        exact = sum(1 for i in range(4) if guess[i] == secret[i])
        remaining_guess = [guess[i] for i in range(4) if guess[i] != secret[i]]
        remaining_secret = [secret[i] for i in range(4) if guess[i] != secret[i]]
        partial = 0
        for value in set(remaining_guess):
            partial += min(remaining_guess.count(value), remaining_secret.count(value))
        return exact, partial
