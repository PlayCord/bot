import discord

NAME = "Tyler's Demise"

LOGGING_ROOT = "playcord"
SERVER_TIMEOUT = 5000

MESSAGE_COMMAND_FAILED = "⛔"
MESSAGE_COMMAND_SUCCEEDED = "✅"

MESSAGE_COMMAND_DISABLE = "disable"
MESSAGE_COMMAND_ENABLE = "enable"
MESSAGE_COMMAND_TOGGLE = "toggle"


OWNERS = []


WELCOME_MESSAGE = [
    (f"Hi! I'm {NAME}!", "Thanks for adding me to your server :D\nHere's some tips on how to get started.\n"
                          "Please note that this introduction (or the bot) dosen't contain details on how to"
                          " use the bot. For that, please check the README (linked below)."),
    ("What is this bot?", f"{NAME} is a bot for playing any variety of quick game on Discord."),
    ("Where's the README?", "Right [here](https://github.com/quantumbagel/PlayCord/blob/master/README.md) :D"),
    ("Who made you?", "[@quantumbagel on Github](https://github.com/quantumbagel)")
]

EMBED_COLOR = discord.Color.from_rgb(255, 87, 51)


CONFIG_BOT_SECRET = "secret"