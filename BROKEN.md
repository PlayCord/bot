# Features

The idea of this file is to store everything known to be broken, as well as the new features I want to add. When this is
empty, I will release 1.0.0

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
  from
  sending anything at all. The issue is that the app command and send message privileges are combined.
- [ ] Have to implement guides for the games on playcord.github.io
- [ ] Better match history summaries. Rather than (place 1st, seat 2nd) we need to have custom summaries for each game
  that
  can include things like "Won by checkmate in 4 moves" or "Won by having the most points at the end of the game" or
  whatever. This would be a string that the game can return at the end of the game to summarize how it was won.
- [ ] Better seating algorithm for games. Some games are assymetric (like Mastermind) and seating can have a big impact
  on
  the game, so we should take that into account when seating players.
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
- [ ] Add a "rematch" button at the end of games that creates a new game-queue with the same players)
- [ ] Game-winning move's edit_game_message call is in a race condition with the thread archival process
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
- [ ] playcord.github.io actual bot page/documentation website