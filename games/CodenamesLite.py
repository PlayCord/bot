import random

from api.Arguments import String
from api.Command import Command
from api.Game import Game, PlayerOrder
from api.MessageComponents import DataTable, Description
from api.Player import Player
from api.Response import Response


class CodenamesLiteGame(Game):
    begin_command_description = "Guess words by teammate clues in a simplified Codenames."
    move_command_group_description = "Commands for Codenames Lite"
    description = "4-player teams, one cluegiver and one guesser per team, race to reveal your words."
    name = "Codenames Lite"
    players = 4
    player_order = PlayerOrder.PRESERVE
    moves = [
        Command(
            name="clue",
            description="Give your team a clue and number.",
            options=[String(argument_name="text", description="Format: word number (e.g. ocean 2)")],
            callback="give_clue",
        ),
        Command(
            name="guess",
            description="Guess one board word.",
            options=[String(argument_name="word", description="Word on the board")],
            callback="guess",
        ),
    ]
    author = "@copilot"
    version = "1.0"
    author_link = "https://github.com/github"
    source_link = "https://github.com/PlayCord/bot/blob/main/games/CodenamesLite.py"
    time = "12min"
    difficulty = "Hard"

    WORD_POOL = [
        "APPLE", "RIVER", "LIGHT", "TRAIN", "CLOUD", "MOUSE", "SWORD", "SPACE", "PLANT", "SHADOW",
        "CASTLE", "BRIDGE", "ORANGE", "SILVER", "FROST", "COMET", "BREAD", "STORM", "CLOCK", "MARBLE",
    ]

    def __init__(self, players: list[Player]) -> None:
        self.players = players
        self.team_a = [players[0], players[2]]
        self.team_b = [players[1], players[3]]
        self.cluegiver = {0: players[0], 1: players[1]}
        self.guesser = {0: players[2], 1: players[3]}
        self.current_team = 0
        self.phase = "clue"
        self.finished = False
        self.winner_team: int | None = None
        self.current_clue = None
        self.remaining_guesses = 0
        self.last_action = f"{self.cluegiver[0].mention} gives the first clue."

        board_words = random.sample(self.WORD_POOL, 16)
        assignments = (["A"] * 6) + (["B"] * 6) + (["N"] * 3) + (["X"] * 1)
        random.shuffle(assignments)
        self.board = {word: {"owner": owner, "revealed": False} for word, owner in zip(board_words, assignments)}
        self.words_left = {0: 6, 1: 6}

    def state(self):
        board = self._render_board()
        if self.finished:
            status = f"🏁 Team {'A' if self.winner_team == 0 else 'B'} wins."
        else:
            status = (
                f"Team {'A' if self.current_team == 0 else 'B'} "
                f"{'clue phase' if self.phase == 'clue' else 'guess phase'}"
            )
        clue_line = f"Clue: {self.current_clue} ({self.remaining_guesses} guess(es) left)" if self.current_clue else "No clue yet."
        description = f"{status}\n{clue_line}\n\n{board}\n\n{self.last_action}"
        table = DataTable(
            {
                self.cluegiver[0]: {"Role:": "A Cluegiver"},
                self.guesser[0]: {"Role:": "A Guesser"},
                self.cluegiver[1]: {"Role:": "B Cluegiver"},
                self.guesser[1]: {"Role:": "B Guesser"},
            }
        )
        return [Description(description), table]

    def current_turn(self) -> Player:
        if self.phase == "clue":
            return self.cluegiver[self.current_team]
        return self.guesser[self.current_team]

    def give_clue(self, player: Player, text: str):
        if self.finished:
            return Response(content="Game is over.", ephemeral=True, delete_after=5)
        if self.phase != "clue":
            return Response(content="You can only give clues during clue phase.", ephemeral=True, delete_after=5)

        parsed = text.strip().split()
        if len(parsed) < 2:
            return Response(content="Use format: `<word> <number>`", ephemeral=True, delete_after=8)
        try:
            number = int(parsed[-1])
        except ValueError:
            return Response(content="Clue must end with a number.", ephemeral=True, delete_after=8)
        if number < 1 or number > 4:
            return Response(content="Clue number must be between 1 and 4.", ephemeral=True, delete_after=8)

        clue_word = " ".join(parsed[:-1]).upper()
        self.current_clue = clue_word
        self.remaining_guesses = number + 1
        self.phase = "guess"
        self.last_action = f"{player.mention} gave clue `{clue_word} {number}`."
        return Response(content="Clue accepted.", ephemeral=True, delete_after=4)

    def guess(self, player: Player, word: str):
        if self.finished:
            return Response(content="Game is over.", ephemeral=True, delete_after=5)
        if self.phase != "guess":
            return Response(content="Wait for your cluegiver to give a clue.", ephemeral=True, delete_after=5)

        guess = word.strip().upper()
        if guess not in self.board:
            return Response(content="That word is not on the board.", ephemeral=True, delete_after=6)

        cell = self.board[guess]
        if cell["revealed"]:
            return Response(content="That word is already revealed.", ephemeral=True, delete_after=6)

        cell["revealed"] = True
        owner = cell["owner"]
        acting_team = self.current_team
        other_team = 1 - acting_team

        if owner == "X":
            self.finished = True
            self.winner_team = other_team
            self.last_action = f"{player.mention} guessed `{guess}` (assassin)."
            return None

        if owner == "A":
            self.words_left[0] -= 1
        elif owner == "B":
            self.words_left[1] -= 1

        if self.words_left[0] == 0:
            self.finished = True
            self.winner_team = 0
            self.last_action = f"{player.mention} revealed `{guess}` and Team A completed their words."
            return None
        if self.words_left[1] == 0:
            self.finished = True
            self.winner_team = 1
            self.last_action = f"{player.mention} revealed `{guess}` and Team B completed their words."
            return None

        if (acting_team == 0 and owner == "A") or (acting_team == 1 and owner == "B"):
            self.remaining_guesses -= 1
            self.last_action = f"{player.mention} guessed `{guess}` correctly."
            if self.remaining_guesses <= 0:
                self._next_team()
        else:
            self.last_action = f"{player.mention} guessed `{guess}` incorrectly."
            self._next_team()
        return None

    def outcome(self):
        if not self.finished:
            return None
        winners = self.team_a if self.winner_team == 0 else self.team_b
        losers = self.team_b if self.winner_team == 0 else self.team_a
        return [winners, losers]

    def _next_team(self):
        self.current_team = 1 - self.current_team
        self.phase = "clue"
        self.current_clue = None
        self.remaining_guesses = 0

    def _render_board(self) -> str:
        words = sorted(self.board.keys())
        rendered = []
        for word in words:
            info = self.board[word]
            if info["revealed"]:
                if info["owner"] == "A":
                    mark = "🟦"
                elif info["owner"] == "B":
                    mark = "🟥"
                elif info["owner"] == "N":
                    mark = "⬜"
                else:
                    mark = "☠️"
                rendered.append(f"{mark}{word}")
            else:
                rendered.append(f"⬛{word}")

        rows = []
        for i in range(0, len(rendered), 4):
            rows.append(" | ".join(rendered[i:i + 4]))
        return "\n".join(rows)
