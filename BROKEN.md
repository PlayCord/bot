# BROKEN.md

The idea of this file is to store everything known to be broken, as well as the new features I want to add. When this is
empty, I will release 1.0.0

## Features (focus on this)

- [ ] No match replay functionality
    - This would require storing the sequence of move JSONs for each game, and then implementing a way to replay those
      moves in a embed with pagination or something. This is a pretty big feature but would be really cool and add a lot
      of value to
      the bot.
    - This also raises the question of how to handle games that have some element of randomness (like card draws or
      something). We would need to store the random seed used for the game and then use that to ensure the replay is
      deterministic.
    - This also opens up the possibility of players sharing replays with each other, which would be really cool. We
      could generate a unique ID for each replay that players can share, and then when someone sees that, they can open
      the replay and view it.
    - Replay ID would be displayed in match history.
    - commands would need to specify whether they actually affect the game (so hand peeks aren't counted etc)
    - Bots would also need to be handled.
- [ ] We need a way to prevent people from sending messages in game thread that are not commands, or people spectating
  from sending anything at all. The issue is that the app command and send message privileges are combined.
- [ ] Better match history summaries. Rather than (place 1st, seat 2nd) we need to have custom summaries for each game
  that can include things like "Won by checkmate in 4 moves" or "Won by passing 5 liberal policies at the end of the
  game"
  or
  whatever. This would be a string that the game can return at the end of the game to summarize how it was won.
- [ ] Better seating algorithm for games. Some games are assymetric (like Mastermind) and seating can have a big impact
  on the game, so we should take that into account when seating players.
    - We would need maybe a way to configure roles for players in each game, and then the seating algorithm would try to
      seat players in a way that balances those roles as much as possible. This would be a pretty complex feature but
      could add a lot of value for certain games. Sometimes it would benefit for this to be random (Secret Hitler), but
      other times we want it to be set. This is something that would be added to the API.
- [ ] Add a feedback command
- [ ] Add customization options for games (board size, wordlist, basically configurable things). This would probably be
  within the matchmaker GUI and not a command (because we don't want to have a /play command for EVERY game
    - There are other questions raised by this:
    - How do we store this information?
    - How do we display it in the matchmaker?
    - How do we handle leaderboards? is there a specified "correct ruleset", or can there be multiple presets? There
      might be several different ways to play a game, and we want that to all be contained within the single game
      instance.
    - This also opens up the possibility of players creating their own custom games by defining the ruleset in a config
      file or something, and then the bot just implements the mechanics of running the game and enforcing the ruleset.
      This is a much more complex feature but could be really cool. Would also force unrated oboviously.
- [ ] Add a "rematch" button at the end of games that creates a new game-queue with the same players
- [ ] Remove the made with love footer in most locations, except for about command etc
- [ ] New custom emojis made for the bot
    - Pixel art, use the blue pixel art duotone
- [ ] Substitution emoji logic is really janky and should be redone, especially for custom emojis
- [ ] Add a better way to limit the bot's scope.
    - Idea for this: Have a single channel the bot "owns."
    - Games can be started from any channel, but the matchmaker will appear in the bot's channel, and all game
      interactions will happen in threads created from that channel.
    - This would also make it easier to find games and keep them organized, and would allow us to remove the (PlayCord)
      from thread names
    - The channel should be a config option that has to be set by a server administrator with /playcord settings
    - If the bot is added to a server, it will include this in the onboarding message that it sends
    - If this channel is not set, attempting to run anything that requires the channel will fail.
- [ ] Database problems
    - Database has wins-losses-ties, which doesn't work very well for FFA
    - Prevent negative ELO ratings
    - Prevent sigma getting too close to 0
    - Basically all of the previous problems require some fixes to the database (leaderboards, customization updates,
      replays, etc)
    - Player total games played gets out of sync with finished games if bot crashes
    - Allow games in the database to be managed by the game registration function. We can also use this to check if bot
      commands would be out of date based on the last database state and update
- [ ] Detect if the synced commands are not equal to the local command tree and auto sync
- [ ] Move the trueskill rating stuff INTO the game class (game.trueskill_parameters) and provide sensible defaults if
  not provided
    - This way game classes are fully modular and can be swapped in/out
- [ ] Error handling
    - If a crash occurs during game setup or something where it is *our* fault (not within a game's code), we still need
      to show an error.
    - This error would be slightly more critical (Internal Bot Exception) and show the logs similar to the existing one.
      Currently most crashes outside of game code fail silently
- [ ] Analytics viewer of some kind
- [ ] More modular game format
    - Currently all of the games have some kind of "game_message" that is entirely controlled by it (within parameters)
    - It might be good/cool to have a more open format where more messages are sent by the bot in the channel as the
      game progresses, maybe with occassional resets ETC.
    - This would also change the bot-provided current turn embed to a ephmeral notification sent by the bot (or a
      message)
    - This would greatly increase the number of possibilities for games.
    - If this was implemented, it would completely replace the current game infastructure but have such a large
      featureset that implementing a game in the current method would also be trivial

## Bugs/Visuals (later)

- [ ] The leaderboard looks like crap
- [ ] Many matrix-like displays (such as the game queue) don't render well on mobile
-

## Website (later)

- [ ] playcord.github.io
    - Needs to contain:
        - [ ] Homepage with bot features and invite link
        - [ ] Bot API docs
        - [ ] Guides for games (already linked to at playcord.github.io/learn/<game>)
        - [x] Privacy policy/TOS
    