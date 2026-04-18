-- PlayCord Database Seed Data
-- Insert default games and initial configuration

-- ============================================================================
-- INSERT DEFAULT GAMES
-- Based on the code registry (GAME_TYPES) and the seeded TrueSkill defaults used during sync_games_from_code()
-- ============================================================================

-- Note: Default MU = 1000, sigma values are relative to MU.

INSERT INTO games (game_name, display_name, min_players, max_players, rating_config, game_metadata)
VALUES
(
    'tictactoe',
    'Tic-Tac-Toe',
    2,
    2,
    jsonb_build_object(
        'sigma', 1.0 / 6.0,
        'beta', 1.0 / 12.0,
        'tau', 1.0 / 100.0,
        'draw', 9.0 / 10.0,
        'default_mu', 1000.0,
        'default_sigma', 166.67
    ),
    jsonb_build_object(
        'description', 'Classic 3x3 grid game where players take turns marking X or O',
        'rules', jsonb_build_array(
            'Players alternate placing their mark (X or O) on a 3x3 grid',
            'First player to get 3 marks in a row (horizontal, vertical, or diagonal) wins',
            'If all 9 squares are filled with no winner, the game is a draw'
        ),
        'emoji', '❌⭕',
        'difficulty', 'easy',
        'avg_duration_seconds', 120
    )
),
(
    'liars',
    'Liar''s Dice',
    2,
    6,
    jsonb_build_object(
        'sigma', 1.0 / 2.5,
        'beta', 1.0 / 5.0,
        'tau', 1.0 / 250.0,
        'draw', 0.0,
        'default_mu', 1000.0,
        'default_sigma', 400.0
    ),
    jsonb_build_object(
        'description', 'Bluffing dice game where players bid on the total number of dice showing a particular face',
        'rules', jsonb_build_array(
            'Each player starts with 5 dice hidden from other players',
            'Players take turns bidding on the total quantity of a specific die face across all players',
            'Each bid must be higher than the previous (either more dice or a higher face value)',
            'A player can challenge the previous bid by calling "Liar!"',
            'If the challenge succeeds, the bidder loses a die; if it fails, the challenger loses a die',
            'Last player with dice remaining wins'
        ),
        'emoji', '🎲',
        'difficulty', 'medium',
        'avg_duration_seconds', 300
    )
),
(
    'test',
    'Test Game',
    1,
    10,
    jsonb_build_object(
        'sigma', 1.0 / 3.0,
        'beta', 1.0 / 5.0,
        'tau', 1.0 / 250.0,
        'draw', 0.0,
        'default_mu', 1000.0,
        'default_sigma', 333.33
    ),
    jsonb_build_object(
        'description', 'Test game for development and debugging purposes',
        'rules', jsonb_build_array(
            'This is a test game used for development',
            'Not intended for actual gameplay'
        ),
        'emoji', '🧪',
        'difficulty', 'test',
        'avg_duration_seconds', 60
    )
),
(
    'connectfour',
    'Connect Four',
    2,
    2,
    jsonb_build_object(
        'sigma', 1.0 / 6.0,
        'beta', 1.0 / 12.0,
        'tau', 1.0 / 120.0,
        'draw', 1.0 / 10.0,
        'default_mu', 1000.0,
        'default_sigma', 166.67
    ),
    jsonb_build_object(
        'description', 'Drop discs into a vertical grid and connect four in a row',
        'rules', jsonb_build_array(
            'Players alternate dropping one disc into a column',
            'Discs stack from the bottom up in each column',
            'First player to connect four horizontally, vertically, or diagonally wins',
            'If board fills with no four-in-a-row, the game is a draw'
        ),
        'emoji', '🔴🟡',
        'difficulty', 'easy',
        'avg_duration_seconds', 240
    )
),
(
    'reversi',
    'Reversi',
    2,
    2,
    jsonb_build_object(
        'sigma', 1.0 / 5.0,
        'beta', 1.0 / 10.0,
        'tau', 1.0 / 150.0,
        'draw', 1.0 / 20.0,
        'default_mu', 1000.0,
        'default_sigma', 200.0
    ),
    jsonb_build_object(
        'description', 'Flip opponent discs by flanking them on an 8x8 board',
        'rules', jsonb_build_array(
            'Players place discs that must flip at least one opponent disc',
            'A player with no legal move is skipped',
            'Game ends when neither player can move',
            'Most discs on board wins'
        ),
        'emoji', '⚫⚪',
        'difficulty', 'medium',
        'avg_duration_seconds', 480
    )
),
(
    'nim',
    'Nim',
    2,
    4,
    jsonb_build_object(
        'sigma', 1.0 / 4.0,
        'beta', 1.0 / 8.0,
        'tau', 1.0 / 150.0,
        'draw', 0.0,
        'default_mu', 1000.0,
        'default_sigma', 250.0
    ),
    jsonb_build_object(
        'description', 'Take stones from piles; the player who takes the final stone wins',
        'rules', jsonb_build_array(
            'On your turn, choose one pile and remove one or more stones',
            'You may remove stones from only one pile per turn',
            'Player taking the last stone wins'
        ),
        'emoji', '🪨',
        'difficulty', 'easy',
        'avg_duration_seconds', 180
    )
),
(
    'mastermind',
    'Mastermind Duel',
    2,
    2,
    jsonb_build_object(
        'sigma', 1.0 / 4.0,
        'beta', 1.0 / 8.0,
        'tau', 1.0 / 180.0,
        'draw', 0.0,
        'default_mu', 1000.0,
        'default_sigma', 250.0
    ),
    jsonb_build_object(
        'description', 'One player sets a secret 4-digit code, the other has limited guesses',
        'rules', jsonb_build_array(
            'Setter chooses a 4-digit code using digits 1-6',
            'Breaker submits guesses and gets exact/partial feedback',
            'Breaker wins by finding full code before attempt limit',
            'Setter wins if breaker runs out of attempts'
        ),
        'emoji', '🧠',
        'difficulty', 'medium',
        'avg_duration_seconds', 360
    )
),
(
    'battleship',
    'Battleship',
    2,
    2,
    jsonb_build_object(
        'sigma', 1.0 / 4.0,
        'beta', 1.0 / 8.0,
        'tau', 1.0 / 180.0,
        'draw', 0.0,
        'default_mu', 1000.0,
        'default_sigma', 250.0
    ),
    jsonb_build_object(
        'description', 'Turn-based naval duel with hidden ship positions',
        'rules', jsonb_build_array(
            'Each player has hidden ships on a private board',
            'Players alternate firing coordinates',
            'Hits damage opponent ships; misses pass turn',
            'First player to sink all enemy ship segments wins'
        ),
        'emoji', '🚢',
        'difficulty', 'medium',
        'avg_duration_seconds', 600
    )
),
(
    'nothanks',
    'No Thanks!',
    3,
    7,
    jsonb_build_object(
        'sigma', 1.0 / 3.0,
        'beta', 1.0 / 6.0,
        'tau', 1.0 / 200.0,
        'draw', 0.0,
        'default_mu', 1000.0,
        'default_sigma', 333.33
    ),
    jsonb_build_object(
        'description', 'Collect cards and chips, aiming for the lowest score',
        'rules', jsonb_build_array(
            'On turn, either take current card and chips or pay one chip to pass',
            'Consecutive card runs count only lowest card in that run',
            'Chips reduce total score',
            'Lowest score wins'
        ),
        'emoji', '🎴',
        'difficulty', 'medium',
        'avg_duration_seconds', 480
    )
),
(
    'blackjack',
    'Blackjack Table',
    2,
    7,
    jsonb_build_object(
        'sigma', 1.0 / 3.0,
        'beta', 1.0 / 6.0,
        'tau', 1.0 / 200.0,
        'draw', 1.0 / 5.0,
        'default_mu', 1000.0,
        'default_sigma', 333.33
    ),
    jsonb_build_object(
        'description', 'Multiplayer blackjack against dealer with hit/stand actions',
        'rules', jsonb_build_array(
            'Players act in turn with hit or stand',
            'Hands over 21 bust immediately',
            'Dealer draws to at least 17 after players finish',
            'Players with better legal totals than dealer rank above losses'
        ),
        'emoji', '🃏',
        'difficulty', 'medium',
        'avg_duration_seconds', 420
    )
),
(
    'codenames',
    'Codenames Lite',
    4,
    4,
    jsonb_build_object(
        'sigma', 1.0 / 3.0,
        'beta', 1.0 / 6.0,
        'tau', 1.0 / 220.0,
        'draw', 0.0,
        'default_mu', 1000.0,
        'default_sigma', 333.33
    ),
    jsonb_build_object(
        'description', 'Two teams race to reveal their words while avoiding assassin',
        'rules', jsonb_build_array(
            'Each team has one cluegiver and one guesser',
            'Cluegiver submits clue word plus number',
            'Guesser reveals words on board based on clue',
            'Revealing assassin loses immediately; revealing all team words wins'
        ),
        'emoji', '🕵️',
        'difficulty', 'hard',
        'avg_duration_seconds', 720
    )
)
ON CONFLICT (game_name) DO UPDATE SET
    display_name = EXCLUDED.display_name,
    min_players = EXCLUDED.min_players,
    max_players = EXCLUDED.max_players,
    rating_config = EXCLUDED.rating_config,
    game_metadata = EXCLUDED.game_metadata,
    updated_at = NOW();


-- ============================================================================
-- VERIFY GAME INSERT
-- ============================================================================
DO $$
DECLARE
    game_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO game_count FROM games;
    RAISE NOTICE 'Inserted % games', game_count;
    
    IF game_count < 11 THEN
        RAISE WARNING 'Expected at least 11 games, but found %', game_count;
    END IF;
END $$;


-- ============================================================================
-- CREATE EXAMPLE TEST DATA (for development/testing only)
-- Comment out or skip this section for production deployment
-- ============================================================================

-- Uncomment below to insert test data for development:

/*
-- Insert test guilds
INSERT INTO guilds (guild_id, settings, is_active) VALUES
(1234567890, '{"default_game": "tictactoe", "leaderboard_public": true}'::jsonb, true),
(9876543210, '{"default_game": "liars", "leaderboard_public": false}'::jsonb, true)
ON CONFLICT (guild_id) DO NOTHING;

-- Insert test users
INSERT INTO users (user_id, username, is_bot, preferences) VALUES
(111111111, 'TestPlayer1', false, '{"notifications": true}'::jsonb),
(222222222, 'TestPlayer2', false, '{"notifications": false}'::jsonb),
(333333333, 'TestPlayer3', false, '{"notifications": true}'::jsonb),
(444444444, 'BotPlayer', true, '{}'::jsonb)
ON CONFLICT (user_id) DO NOTHING;

-- Initialize test ratings
INSERT INTO user_game_ratings (user_id, guild_id, game_id, mu, sigma, matches_played)
SELECT 
    u.user_id,
    g.guild_id,
    gm.game_id,
    (gm.rating_config->>'default_mu')::DOUBLE PRECISION,
    (gm.rating_config->>'default_sigma')::DOUBLE PRECISION,
    0
FROM users u
CROSS JOIN guilds g
CROSS JOIN games gm
WHERE u.user_id IN (111111111, 222222222, 333333333)
  AND gm.game_name IN ('tictactoe', 'liars')
ON CONFLICT (user_id, guild_id, game_id) DO NOTHING;

RAISE NOTICE 'Test data inserted successfully';
*/


-- ============================================================================
-- ANALYTICS EVENT TYPES DOCUMENTATION
-- Common event types that will be recorded
-- ============================================================================
COMMENT ON TABLE analytics_events IS 
'Event types include:
- game_started: New game created
- game_completed: Game finished successfully
- game_abandoned: Game abandoned by players
- matchmaking_joined: Player joined matchmaking queue
- matchmaking_left: Player left matchmaking queue
- matchmaking_matched: Players matched for a game
- player_joined: Player joined a match
- player_left: Player left a match
- move_made: Player made a move
- command_used: Discord command executed
- error_occurred: Error during game operation
- bot_started: Bot initialized
- guild_joined: Bot added to new guild
- guild_left: Bot removed from guild
- rating_updated: Player rating changed
- skill_decay_applied: Inactive player sigma increased
';


-- ============================================================================
-- INITIAL DATABASE STATISTICS
-- ============================================================================
DO $$
DECLARE
    table_count INTEGER;
    index_count INTEGER;
    constraint_count INTEGER;
BEGIN
    -- Count tables
    SELECT COUNT(*) INTO table_count
    FROM information_schema.tables
    WHERE table_schema = 'public' 
      AND table_type = 'BASE TABLE';
    
    -- Count indexes
    SELECT COUNT(*) INTO index_count
    FROM pg_indexes
    WHERE schemaname = 'public';
    
    -- Count constraints
    SELECT COUNT(*) INTO constraint_count
    FROM information_schema.table_constraints
    WHERE table_schema = 'public';
    
    RAISE NOTICE '===========================================';
    RAISE NOTICE 'PlayCord Database Initialized Successfully';
    RAISE NOTICE '===========================================';
    RAISE NOTICE 'Tables: %', table_count;
    RAISE NOTICE 'Indexes: %', index_count;
    RAISE NOTICE 'Constraints: %', constraint_count;
    RAISE NOTICE 'Games available: %', (SELECT COUNT(*) FROM games);
    RAISE NOTICE '===========================================';
END $$;