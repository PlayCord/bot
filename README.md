# PlayCord

_a discord bot for simple games_

by [@quantumbagel](https://github.com/quantumbagel)

### Sections to add to README

* Bot usage (within Discord)
* API usage (within Python)
* Features
* Dependencies
* List of games (both planned and implemented)

### Project Aims

PlayCord aims to become a bot capable of playing any paper/pencil game on Discord.
We will accomplish this using the following:

* Easy-to-understand API for creating games
* Backend syntax/caching handled by PlayCord
* SVG rendering
* MySQL database for leaderboard
* TrueSkill rating system

### Current TODOs

- [ ] Need to read up on TrueSkill and fix Player.get_formatted_elo
- [ ] Player order is currently randomized, this should be changed for some games (API)
- [ ] Emojis
    - [ ] API support for registering emojis
    - [ ] API support for getting emojis
    - [ ] Buttons need emojis
    - [ ] Rip off Tyler
- [ ] Prevent certain thread members (that aren't in game) from sending messages
- [ ] Heck, prevent anyone from just "sending messages" in game threads?
    - [x] From what I've found, this is impossible?
- [ ] Better permission checking for commands
    - [ ] This includes
        - [ ] the ability to start games (or inability)
        - [ ] the ability to join games (or inability)
    - [ ] Also, prevent the wrong move command from even bothering to check in the wrong channel and just failing it
- [ ] Leaderboards
    - [ ] /leaderboard \<game\> command
        - [ ] top x, top worldwide, server
        - [ ] pagination, etc
    - [ ] Top X globally ranked message in the get_formatted_elo function, etc
- [ ] /help command for bot
- [ ] Textify more text areas, including
    - [ ] Game started text
    - [ ] Button text
    - [ ] Game over text
- [ ] /playcord catalog <PAGE> for list of games, which is paginated
- [ ] /playcord profile <USER> for data on user
- [ ] Rework the MySQL database to something else, because it SUCKS
- [ ] Add analytic event system
- [ ] Cross-server matchmaking
- [ ] Ability to change game settings (/playcord settings), such as the type of game, whether rated, and private status
- [ ] Add variables for ALL string fields in constants.py
- [ ] API Docs
- [ ] Other games:
    - [ ] Liar's Dice
    - [ ] Poker (Texas Holdem)
    - [ ] Chess

If you find this project cool, I would love it if you starred my repository 🤩