import discord


class DynamicButtonView(discord.ui.View):
    """
    Hoo boy
    this is cursed
    "Simple" way of making a button-only persistent view
    Only took 3 hours :)
    """
    def __init__(self, buttons):
        super().__init__(timeout=None)

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

    async def _null_callback(self, interaction: discord.Interaction):
        """
        TODO: add logging here. This is a NULL callback
        :param interaction: discord context
        :return:
        """
        pass

    async def _fail_callback(self, interaction: discord.Interaction):
        """
        If a "dead" view is interacted, simply disable each component and update the message
        also send an ephemeral message to the interacter
        :param interaction: discord context
        :return: nothing
        """
        embed = interaction.message.embeds[0] # There can only be one... embed :0
        for child in self.children:  # Disable all children
            child.disabled = True

        await interaction.response.edit_message(embed=embed, view=self)  # Update message, because you can't autoupdate

        msg = await interaction.followup.send(content="That interaction is no longer active due to a bot restart!"
                                                " Please create a new interaction :)", ephemeral=True)

        await msg.delete(delay=10)


class MatchmakingView(DynamicButtonView):
    def __init__(self, join_button_callback=None, leave_button_callback=None,
                 start_button_callback=None, can_start=True):
        super().__init__([{"label": "Join", "style": discord.ButtonStyle.gray, "id": "join", "callback": join_button_callback},
                          {"label": "Leave", "style": discord.ButtonStyle.gray, "id": "leave", "callback": leave_button_callback},
                          {"label": "Start", "style": discord.ButtonStyle.blurple, "id": "start", "callback": start_button_callback, "disabled": not can_start}])


class InviteView(DynamicButtonView):
    def __init__(self, join_button_id=None, game_link=None):
        super().__init__([{"label": "Join Game", "style": discord.ButtonStyle.blurple, "id": join_button_id, "callback": "none"},
                          {"label": "Go To Game (won't join)", "style": discord.ButtonStyle.gray, "link": game_link}])


class SpectateView(DynamicButtonView):
    def __init__(self, spectate_button_id=None, peek_button_id=None, game_link=None):
        super().__init__([{"label": "Spectate Game", "style": discord.ButtonStyle.blurple, "id": spectate_button_id, "callback": "none"},
                          {"label": "Peek", "style": discord.ButtonStyle.gray, "id": peek_button_id, "callback": "none"},
                          {"label": "Go To Game (won't join)", "style": discord.ButtonStyle.gray, "link": game_link}])