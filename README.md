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

PlayCord aims to become a bot capable of playing any game on Discord.
We will accomplish this using the following:

* Easy- [ ]to- [ ]understand API for creating games
* Backend syntax/caching handled by PlayCord
* SVG rendering
* MySQL database for leaderboard
* TrueSkill rating system


### Current TODOs
- [ ] Property class is essentially just a number. It can and should have more functionality (linked nodes, etc)
- [ ] Game class doesn't represent current API, TicTacToeGame does
- [ ] Need to read up on TrueSkill and fix Player.get_formatted_elo
- [ ] Player order is currently randomized, this should be changed for some games (API)
- [ ] Bug with TicTacToeGame.generate_game_picture prevents game board SVG from being updated
- [ ] Missing many InputTypes, most notably Integer
- [ ] Autocomplete does not consider player input, the literal reason it was added.
- [ ] Game over state not implemented.
- [ ] The "spectate" button doesn't work and the text associated with it is nonsense
- [ ] Emojis
  - [ ] API support for registering emojis
  - [ ] API support for getting emojis
  - [ ] Buttons need emojis
  - [ ] Rip off Tyler
- [ ] Dynamic game thread names
  - [ ] Include names of players? time? bot name?
- [ ] Lock threads on game end
- [ ] Prevent certain thread members (that aren't in game) from sending messages
- [ ] Heck, prevent anyone from just "sending messages" in game threads?
  - [ ] From what I've found, this is impossible
- [ ] Remove the "Setting up stuff" message edit event for main thread and private threads
  - [ ] We probably don't even need this, it takes more time than just a defer()
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
- [ ] Bot presence
  - [ ] yea, pretty simple i know
- [ ] Add description to bot
- [ ] /help command for bot
- [ ] Finish this stupid README
- [ ] Textify more text areas, including
  - [ ] Game started text
  - [ ] Button text
  - [ ] Game over text
- [ ] Catch-all error response if there is a crash, instead of "interaction failed"
  - [ ] Also, some method of logging crashes
- [ ] Add comments and docstrings to code