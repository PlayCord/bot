import typing

import discord


class DynamicButtonDict(typing.TypedDict, total=False):
    label: str
    style: discord.ButtonStyle
    id: str
    emoji: str | discord.PartialEmoji
    disabled: bool
    callback: typing.Callable | str
    link: str


class DynamicButtonView(discord.ui.View):
    """
    Dynamic button view: this is PAIN
    """

    def __init__(self, buttons: list[DynamicButtonDict]) -> None:
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

    def __init__(self, join_button_callback=None, leave_button_callback=None,
                 start_button_callback=None, can_start=True) -> None:
        """
        Create a matchmaking view
        :param join_button_callback: function that will be called when the join button is clicked
        :param leave_button_callback: function that will be called when the leave button is clicked
        :param start_button_callback: function that will be called when the start button is clicked
        :param can_start: whether the game can be started
        """
        super().__init__([{"label": "Join", "style": discord.ButtonStyle.gray, "id": "join",
                           "callback": join_button_callback},
                          {"label": "Leave", "style": discord.ButtonStyle.gray, "id": "leave",
                           "callback": leave_button_callback},
                          {"label": "Start", "style": discord.ButtonStyle.blurple, "id": "start",
                           "callback": start_button_callback, "disabled": not can_start}])


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
        super().__init__([{"label": "Join Game", "style": discord.ButtonStyle.blurple,
                           "id": join_button_id, "callback": "none"},
                          {"label": "Go To Game (won't join)",
                           "style": discord.ButtonStyle.gray, "link": game_link}])


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
        super().__init__([{"label": "Spectate Game", "style": discord.ButtonStyle.blurple,
                           "id": spectate_button_id, "callback": "none"},
                          {"label": "Peek", "style": discord.ButtonStyle.gray, "id": peek_button_id,
                           "callback": "none"},
                          {"label": "Go To Game (won't join)", "style": discord.ButtonStyle.gray,
                           "link": game_link}])
