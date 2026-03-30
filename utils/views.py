import discord

from utils.emojis import get_button_emoji


class DynamicButtonView(discord.ui.View):
    """
    Dynamic button view: this is PAIN
    """

    def __init__(self, buttons: list[dict]) -> None:
        """
        Create a dynamic button view
        :param buttons: list of buttons as dictionaries
        look at class D
        """
        super().__init__(timeout=None)  # timeout=None required for persistent views, per discord docs

        # Register buttons to view
        for button in buttons:
            for argument in ["label", "style", "id", "emoji", "disabled", "callback", "link"]:
                if argument not in button.keys():
                    if argument == "disabled":
                        button[argument] = False
                        continue
                    button[argument] = None

            item = discord.ui.Button(label=button["label"], style=button["style"],
                                     custom_id=button["id"], emoji=button["emoji"], disabled=button["disabled"],
                                     url=button["link"])
            if button["callback"] is None:
                item.callback = self._fail_callback
            elif button["callback"] == "none":
                item.callback = self._null_callback
            else:
                item.callback = button["callback"]

            self.add_item(item)

    async def _null_callback(self, interaction: discord.Interaction) -> None:
        """
        Null callback
        :param interaction: discord context
        :return: Nothing
        """
        pass

    async def _fail_callback(self, interaction: discord.Interaction) -> None:
        """
        If a "dead" view is interacted, simply disable each component and update the message
        also send an ephemeral message to the interacter
        :param interaction: discord context
        :return: nothing
        """
        embed = interaction.message.embeds[0]  # There can only be one... embed :O

        for child in self.children:  # Disable all children via drop kicking
            child.disabled = True

        await interaction.response.edit_message(embed=embed, view=self)  # Update message, because you can't autoupdate

        msg = await interaction.followup.send(content="That interaction is no longer active due to a bot restart!"
                                                      " Please create a new interaction :)", ephemeral=True)

        await msg.delete(delay=10)  # autodelete message


class MatchmakingView(DynamicButtonView):
    """
    View for matchmaking message
    """

    def __init__(self, join_button_id=None, leave_button_id=None,
                 start_button_id=None, can_start=True) -> None:
        """
        Create a matchmaking view
        :param join_button_id: id of the join button
        :param leave_button_id: id of the leave button
        :param start_button_id: id of the start button
        :param can_start: whether the game can be started
        """
        super().__init__([
            {"label": "Join", "style": discord.ButtonStyle.gray, "id": join_button_id,
             "emoji": get_button_emoji("join"), "callback": "none"},
            {"label": "Leave", "style": discord.ButtonStyle.gray, "id": leave_button_id,
             "emoji": get_button_emoji("leave"), "callback": "none"},
            {"label": "Start", "style": discord.ButtonStyle.blurple, "id": start_button_id,
             "emoji": get_button_emoji("start"), "callback": "none", "disabled": not can_start}
        ])


class InviteView(DynamicButtonView):
    """
    View for invitation DM
    """

    def __init__(self, join_button_id=None, game_link=None) -> None:
        """
        Create a invite view
        :param join_button_id: the custom ID of the join button
        :param game_link: the link to the game
        """
        super().__init__([
            {"label": "Join Game", "style": discord.ButtonStyle.blurple,
             "id": join_button_id, "emoji": get_button_emoji("join"), "callback": "none"},
            {"label": "Go To Game (won't join)",
             "style": discord.ButtonStyle.gray, "link": game_link}
        ])


class SpectateView(DynamicButtonView):
    """
    View for status message
    """

    def __init__(self, spectate_button_id=None, peek_button_id=None, game_link=None) -> None:
        """
        Create a spectate view
        :param spectate_button_id: custom ID of the spectate button
        :param peek_button_id: custom ID of the peek button
        :param game_link: the link to the game
        """
        super().__init__([
            {"label": "Spectate Game", "style": discord.ButtonStyle.blurple,
             "id": spectate_button_id, "emoji": get_button_emoji("spectate"), "callback": "none"},
            {"label": "Peek", "style": discord.ButtonStyle.gray, "id": peek_button_id,
             "emoji": get_button_emoji("peek"), "callback": "none"},
            {"label": "Go To Game (won't join)", "style": discord.ButtonStyle.gray,
             "link": game_link}
        ])


class PaginationView(DynamicButtonView):
    """
    Persistent pagination view with First/Previous/Next/Last buttons.
    Uses timeout=None to survive bot restarts.
    """

    def __init__(self, command: str, guild_id: int, user_id: int, current_page: int,
                 max_pages: int, params_hash: str, callback_handler):
        """
        Initialize pagination view.
        
        Args:
            command: Command name (catalog, leaderboard, history)
            guild_id: Guild ID for validation
            user_id: User ID who invoked the command (only they can interact)
            current_page: Current page number (1-indexed)
            max_pages: Total number of pages
            params_hash: Hash of additional parameters (game, user, days, etc.)
            callback_handler: Async function to regenerate embed for a new page
        """
        self.command = command
        self.guild_id = guild_id
        self.user_id = user_id
        self.current_page = current_page
        self.max_pages = max_pages
        self.params_hash = params_hash
        self.callback_handler = callback_handler

        from configuration.constants import (
            BUTTON_PREFIX_PAGINATION_FIRST,
            BUTTON_PREFIX_PAGINATION_PREV,
            BUTTON_PREFIX_PAGINATION_NEXT,
            BUTTON_PREFIX_PAGINATION_LAST
        )

        super().__init__([
            {
                "label": "First",
                "emoji": "⏮️",
                "style": discord.ButtonStyle.gray,
                "id": f"{BUTTON_PREFIX_PAGINATION_FIRST}{command}/{guild_id}/{user_id}/1/{max_pages}/{params_hash}",
                "disabled": (current_page == 1),
                "callback": self._first_callback,
            },
            {
                "label": "Previous",
                "emoji": "◀️",
                "style": discord.ButtonStyle.primary,
                "id": f"{BUTTON_PREFIX_PAGINATION_PREV}{command}/{guild_id}/{user_id}/{current_page}/{max_pages}/{params_hash}",
                "disabled": (current_page == 1),
                "callback": self._prev_callback,
            },
            {
                "label": "Next",
                "emoji": "▶️",
                "style": discord.ButtonStyle.primary,
                "id": f"{BUTTON_PREFIX_PAGINATION_NEXT}{command}/{guild_id}/{user_id}/{current_page}/{max_pages}/{params_hash}",
                "disabled": (current_page >= max_pages),
                "callback": self._next_callback,
            },
            {
                "label": "Last",
                "emoji": "⏭️",
                "style": discord.ButtonStyle.gray,
                "id": f"{BUTTON_PREFIX_PAGINATION_LAST}{command}/{guild_id}/{user_id}/{max_pages}/{max_pages}/{params_hash}",
                "disabled": (current_page >= max_pages),
                "callback": self._last_callback,
            },
        ])

    def _validate_interaction(self, interaction: discord.Interaction) -> bool:
        """Validate that the interaction is from the command invoker."""
        if interaction.user.id != self.user_id:
            return False
        if interaction.guild_id != self.guild_id:
            return False
        return True

    async def _first_callback(self, interaction: discord.Interaction):
        """Navigate to first page."""
        if not self._validate_interaction(interaction):
            await interaction.response.send_message(
                "You cannot interact with another user's pagination buttons.",
                ephemeral=True
            )
            return

        await self.callback_handler(interaction, 1)

    async def _prev_callback(self, interaction: discord.Interaction):
        """Navigate to previous page."""
        if not self._validate_interaction(interaction):
            await interaction.response.send_message(
                "You cannot interact with another user's pagination buttons.",
                ephemeral=True
            )
            return

        new_page = max(1, self.current_page - 1)
        await self.callback_handler(interaction, new_page)

    async def _next_callback(self, interaction: discord.Interaction):
        """Navigate to next page."""
        if not self._validate_interaction(interaction):
            await interaction.response.send_message(
                "You cannot interact with another user's pagination buttons.",
                ephemeral=True
            )
            return

        new_page = min(self.max_pages, self.current_page + 1)
        await self.callback_handler(interaction, new_page)

    async def _last_callback(self, interaction: discord.Interaction):
        """Navigate to last page."""
        if not self._validate_interaction(interaction):
            await interaction.response.send_message(
                "You cannot interact with another user's pagination buttons.",
                ephemeral=True
            )
            return

        await self.callback_handler(interaction, self.max_pages)


def parse_pagination_custom_id(custom_id: str) -> dict:
    """
    Parse pagination button custom_id to extract components.
    
    Format: <prefix><command>/<guild_id>/<user_id>/<page>/<max_pages>/<params_hash>
    
    Returns:
        dict with keys: command, guild_id, user_id, page, max_pages, params_hash
        
    Raises:
        ValueError: If custom_id format is invalid
    """
    from configuration.constants import (
        BUTTON_PREFIX_PAGINATION_FIRST,
        BUTTON_PREFIX_PAGINATION_PREV,
        BUTTON_PREFIX_PAGINATION_NEXT,
        BUTTON_PREFIX_PAGINATION_LAST
    )

    # Remove prefix
    for prefix in [BUTTON_PREFIX_PAGINATION_FIRST, BUTTON_PREFIX_PAGINATION_PREV,
                   BUTTON_PREFIX_PAGINATION_NEXT, BUTTON_PREFIX_PAGINATION_LAST]:
        if custom_id.startswith(prefix):
            custom_id = custom_id[len(prefix):]
            break

    parts = custom_id.split('/')
    if len(parts) != 6:
        raise ValueError(f"Invalid pagination custom_id format: expected 6 parts, got {len(parts)}")

    return {
        'command': parts[0],
        'guild_id': int(parts[1]),
        'user_id': int(parts[2]),
        'page': int(parts[3]),
        'max_pages': int(parts[4]),
        'params_hash': parts[5]
    }
