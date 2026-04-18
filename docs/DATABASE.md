# PlayCord Database Documentation

## Overview

PlayCord uses **PostgreSQL 14+** (recommended: 16) for persistent storage of game data, user ratings, match history, and
analytics. Runtime access now flows through `playcord/infrastructure/db/`, where `PoolManager` owns connections,
`MigrationRunner` handles startup maintenance, and repositories (`PlayerRepository`, `GameRepository`, `MatchRepository`,
`ReplayRepository`, `AnalyticsRepository`) provide the application-layer interface.

The database is designed for:

- **Extensibility**: Easy to add new games and features
- **Data Integrity**: Comprehensive constraints and foreign keys
- **Performance**: Strategic indexes for common queries
- **Auditability**: Full move history and rating changes
- **Scalability**: Connection pooling and optimized queries

See [DATABASE_DECISIONS.md](DATABASE_DECISIONS.md) for the current authority decisions around replay storage,
TrueSkill configuration, and preset/variant leaderboard modeling.

## Architecture

### Database Schema Version: 2.4

The schema consists of:

- **12 core tables** for data storage
- **10 views** for common query patterns
- **12 PostgreSQL functions** for automation and maintenance
- **25+ indexes** for query optimization
- **20+ constraints** for data validation

---

## Table Reference

### Core Tables

#### 1. `guilds`

Discord servers where the bot is installed.

| Column     | Type        | Description                         |
|------------|-------------|-------------------------------------|
| guild_id   | BIGINT (PK) | Discord guild/server ID             |
| joined_at  | TIMESTAMPTZ | When bot joined the guild           |
| settings   | JSONB       | Guild preferences and configuration |
| is_active  | BOOLEAN     | Whether guild is active             |
| created_at | TIMESTAMPTZ | Record creation time                |
| updated_at | TIMESTAMPTZ | Last update time                    |

**Indexes:**

- `idx_guilds_active` on (is_active, joined_at DESC)

**Example settings JSON:**

```json
{
  "default_game": "tictactoe",
  "leaderboard_public": true,
  "allow_cross_guild_matchmaking": false
}
```

---

#### 2. `users`

Discord users who interact with the bot.

| Column      | Type                  | Description                   |
|-------------|-----------------------|-------------------------------|
| user_id     | BIGINT (PK)           | Discord user ID               |
| username    | VARCHAR(100) NOT NULL | Discord username              |
| joined_at   | TIMESTAMPTZ           | When user first joined        |
| preferences | JSONB                 | User preferences and settings |
| is_bot      | BOOLEAN               | Whether user is a bot         |
| is_active   | BOOLEAN               | Whether user is active        |
| created_at  | TIMESTAMPTZ           | Record creation time          |
| updated_at  | TIMESTAMPTZ           | Last update time              |

**Constraints:**

- `chk_username_not_empty`: LENGTH(TRIM(username)) > 0

**Indexes:**

- `idx_users_active` on (is_active, joined_at DESC)
- `idx_users_username` on (username varchar_pattern_ops)

**Example preferences JSON:**

```json
{
  "notification_settings": {
    "match_invites": true,
    "rating_changes": false
  },
  "default_rated": true
}
```

---

#### 3. `games`

Registry of available games in the bot.

| Column        | Type                | Description                                |
|---------------|---------------------|--------------------------------------------|
| game_id       | SERIAL (PK)         | Unique game identifier                     |
| game_name     | VARCHAR(100) UNIQUE | Internal game name (lowercase, snake_case) |
| display_name  | VARCHAR(200)        | User-facing display name                   |
| min_players   | INTEGER             | Minimum number of players                  |
| max_players   | INTEGER             | Maximum number of players                  |
| rating_config | JSONB               | TrueSkill configuration parameters         |
| game_metadata | JSONB               | Game description, rules, etc.              |
| is_active     | BOOLEAN             | Whether game is available                  |
| created_at    | TIMESTAMPTZ         | Record creation time                       |
| updated_at    | TIMESTAMPTZ         | Last update time                           |

**Constraints:**

- `chk_game_players`: min_players >= 1 AND max_players >= min_players
- `chk_game_name_format`: game_name ~ '^[a-z][a-z0-9_]*$'
- `chk_rating_config_keys`: Must have 'sigma', 'beta', 'tau', 'draw' keys

**Indexes:**

- `idx_games_active` on (is_active, game_name)

**Example rating_config:**

```json
{
  "sigma": 0.1667,
  "beta": 0.0833,
  "tau": 0.01,
  "draw": 0.9
}
```

**Example game_metadata:**

```json
{
  "description": "Classic Xs and Os",
  "rules": [
    "Players alternate placing X and O",
    "First to get 3 in a row wins"
  ],
  "emoji": "❌"
}
```

---

#### 4. `user_game_ratings`

Per-user, per-guild, per-game TrueSkill ratings. This is the **core rating table**.

| Column              | Type             | Description                                |
|---------------------|------------------|--------------------------------------------|
| rating_id           | BIGSERIAL (PK)   | Unique rating record ID                    |
| user_id             | BIGINT NOT NULL  | Reference to users                         |
| guild_id            | BIGINT NOT NULL  | Reference to guilds                        |
| game_id             | INTEGER NOT NULL | Reference to games                         |
| mu                  | DOUBLE PRECISION | TrueSkill skill estimate (default: 1000.0) |
| sigma               | DOUBLE PRECISION | TrueSkill uncertainty (default: 333.33)    |
| matches_played      | INTEGER          | Total matches played                       |
| wins                | INTEGER          | Total wins                                 |
| losses              | INTEGER          | Total losses                               |
| draws               | INTEGER          | Total draws                                |
| last_played         | TIMESTAMPTZ      | When user last played this game            |
| last_sigma_increase | TIMESTAMPTZ      | When sigma was last increased (decay)      |
| created_at          | TIMESTAMPTZ      | Record creation time                       |
| updated_at          | TIMESTAMPTZ      | Last update time                           |

**Constraints:**

- `uq_user_guild_game` UNIQUE (user_id, guild_id, game_id)
- `chk_rating_positive`: mu > 0 AND sigma > 0
- `chk_matches_counts`: wins + losses + draws <= matches_played
- Foreign keys to users, guilds, games (ON DELETE CASCADE)

**Indexes:**

- `idx_rating_leaderboard` on (guild_id, game_id, mu-3*sigma DESC) WHERE matches_played >= 5
- `idx_rating_user_activity` on (user_id, game_id, last_played DESC)
- `idx_rating_inactive` on (last_played) WHERE last_played IS NOT NULL
- `idx_rating_game_guild` on (game_id, guild_id)

**Notes:**

- Conservative rating = mu - 3*sigma (used for leaderboard ranking)
- Higher mu = better skill estimate
- Lower sigma = more certain about skill
- Sigma increases over time for inactive players (skill decay)

---

#### 5. `matches`

Game matches (both in-progress and completed).

| Column      | Type             | Description                            |
|-------------|------------------|----------------------------------------|
| match_id    | BIGSERIAL (PK)   | Unique match identifier                |
| game_id     | INTEGER NOT NULL | Reference to games                     |
| guild_id    | BIGINT NOT NULL  | Reference to guilds                    |
| channel_id  | BIGINT NOT NULL  | Discord channel where match is hosted  |
| thread_id   | BIGINT           | Discord thread ID (optional)           |
| started_at  | TIMESTAMPTZ      | When match started                     |
| ended_at    | TIMESTAMPTZ      | When match ended (NULL if in progress) |
| status      | VARCHAR(20)      | Match status                           |
| is_rated    | BOOLEAN          | Whether match affects ratings          |
| game_config | JSONB            | Game-specific configuration            |
| final_state | JSONB            | Final game state/board                 |
| metadata    | JSONB            | Additional metadata                    |
| created_at  | TIMESTAMPTZ      | Record creation time                   |

**Constraints:**

- `chk_match_status`: status IN ('in_progress', 'completed', 'abandoned', 'disputed')
- `chk_match_end_time`: ended_at IS NULL OR ended_at > started_at
- Foreign keys to games, guilds (ON DELETE CASCADE)

**Indexes:**

- `idx_matches_guild_game` on (guild_id, game_id, ended_at DESC NULLS LAST)
- `idx_matches_status` on (status, started_at DESC) WHERE status = 'in_progress'
- `idx_matches_recent` on (ended_at DESC) WHERE ended_at IS NOT NULL
- `idx_matches_channel` on (channel_id, status)

**Example metadata:**

```json
{
  "spectators": [
    123456789,
    987654321
  ],
  "timeout_seconds": 300,
  "rematch_requested": false
}
```

---

#### 6. `match_participants`

Players in each match with their results and rating changes.

| Column         | Type             | Description                            |
|----------------|------------------|----------------------------------------|
| participant_id | BIGSERIAL (PK)   | Unique participant ID                  |
| match_id       | BIGINT NOT NULL  | Reference to matches                   |
| user_id        | BIGINT NOT NULL  | Reference to users                     |
| player_number  | INTEGER NOT NULL | Turn order (1-indexed)                 |
| final_ranking  | INTEGER          | Final ranking (1=winner, higher=worse) |
| score          | DOUBLE PRECISION | Numeric score (optional)               |
| mu_before      | DOUBLE PRECISION | Rating mu before match                 |
| sigma_before   | DOUBLE PRECISION | Rating sigma before match              |
| mu_delta       | DOUBLE PRECISION | Change in mu from match                |
| sigma_delta    | DOUBLE PRECISION | Change in sigma from match             |
| joined_at      | TIMESTAMPTZ      | When player joined match               |

**Constraints:**

- `uq_match_user` UNIQUE (match_id, user_id)
- `uq_match_player_number` UNIQUE (match_id, player_number)
- `chk_player_number`: player_number >= 1
- `chk_final_ranking`: final_ranking IS NULL OR final_ranking >= 1
- Foreign keys to matches, users (ON DELETE CASCADE)

**Indexes:**

- `idx_participants_match` on (match_id, player_number)
- `idx_participants_user` on (user_id, match_id DESC)
- `idx_participants_ranking` on (match_id, final_ranking)

**Notes:**

- Ties allowed: multiple players can have same final_ranking
- mu_delta and sigma_delta calculated by TrueSkill algorithm

---

#### 7. `moves`

Full move history for game replay and auditing.

| Column           | Type             | Description                                |
|------------------|------------------|--------------------------------------------|
| move_id          | BIGSERIAL (PK)   | Unique move identifier                     |
| match_id         | BIGINT NOT NULL  | Reference to matches                       |
| user_id          | BIGINT           | Reference to users (NULL for system moves) |
| move_number      | INTEGER NOT NULL | Sequence number (1-indexed)                |
| move_data        | JSONB NOT NULL   | Game-specific move data                    |
| game_state_after | JSONB            | Game state after move (optional)           |
| timestamp        | TIMESTAMPTZ      | When move was made                         |
| time_taken_ms    | INTEGER          | Thinking time in milliseconds              |

**Constraints:**

- `uq_match_move_number` UNIQUE (match_id, move_number)
- `chk_move_number`: move_number >= 1
- `chk_time_taken`: time_taken_ms IS NULL OR time_taken_ms >= 0
- Foreign keys to matches, users (ON DELETE CASCADE)

**Indexes:**

- `idx_moves_match_sequence` on (match_id, move_number ASC)
- `idx_moves_user` on (user_id, timestamp DESC)
- `idx_moves_timestamp` on (timestamp DESC)

**Example move_data (Chess):**

```json
{
  "from": "e2",
  "to": "e4",
  "piece": "pawn",
  "notation": "e4"
}
```

**Example move_data (Tic-Tac-Toe):**

```json
{
  "position": 4,
  "row": 1,
  "col": 1,
  "symbol": "X"
}
```

---

#### 8. `analytics_events`

Event tracking for monitoring and analytics.

| Column     | Type                  | Description                     |
|------------|-----------------------|---------------------------------|
| event_id   | BIGSERIAL (PK)        | Unique event identifier         |
| event_type | VARCHAR(100) NOT NULL | Type of event                   |
| timestamp  | TIMESTAMPTZ           | When event occurred             |
| user_id    | BIGINT                | Reference to users (optional)   |
| guild_id   | BIGINT                | Reference to guilds (optional)  |
| game_id    | INTEGER               | Reference to games (optional)   |
| match_id   | BIGINT                | Reference to matches (optional) |
| metadata   | JSONB                 | Event-specific data             |

**Constraints:**

- Foreign keys to users, guilds, games, matches (ON DELETE SET NULL)

**Indexes:**

- `idx_analytics_type_time` on (event_type, timestamp DESC)
- `idx_analytics_user` on (user_id, timestamp DESC) WHERE user_id IS NOT NULL
- `idx_analytics_guild` on (guild_id, timestamp DESC) WHERE guild_id IS NOT NULL
- `idx_analytics_timestamp` on (timestamp DESC)

**Common event_type values:**

- `game_started`, `game_completed`, `game_abandoned`
- `matchmaking_requested`, `matchmaking_matched`, `matchmaking_timeout`
- `rating_updated`, `skill_decay_applied`
- `command_used`, `error_occurred`

**Example metadata:**

```json
{
  "duration_seconds": 120,
  "error_message": "Timeout waiting for opponent",
  "command_name": "/play"
}
```

---

#### 9. `rating_history`

Historical audit trail of all rating changes.

| Column       | Type             | Description              |
|--------------|------------------|--------------------------|
| history_id   | BIGSERIAL (PK)   | Unique history record ID |
| user_id      | BIGINT NOT NULL  | Reference to users       |
| guild_id     | BIGINT NOT NULL  | Reference to guilds      |
| game_id      | INTEGER NOT NULL | Reference to games       |
| match_id     | BIGINT NOT NULL  | Reference to matches     |
| mu_before    | DOUBLE PRECISION | Mu before match          |
| sigma_before | DOUBLE PRECISION | Sigma before match       |
| mu_after     | DOUBLE PRECISION | Mu after match           |
| sigma_after  | DOUBLE PRECISION | Sigma after match        |
| timestamp    | TIMESTAMPTZ      | When change occurred     |

**Constraints:**

- Foreign keys to users, guilds, games, matches (ON DELETE CASCADE)

**Indexes:**

- `idx_history_user_game` on (user_id, game_id, timestamp DESC)
- `idx_history_match` on (match_id)
- `idx_history_guild_game` on (guild_id, game_id, timestamp DESC)

**Usage:**

- View rating progression over time
- Generate rating trend charts
- Audit rating changes

---

#### 10. `global_ratings`

Cross-guild aggregated ratings using Bayesian combination.

| Column           | Type             | Description                     |
|------------------|------------------|---------------------------------|
| global_rating_id | BIGSERIAL (PK)   | Unique global rating ID         |
| user_id          | BIGINT NOT NULL  | Reference to users              |
| game_id          | INTEGER NOT NULL | Reference to games              |
| global_mu        | DOUBLE PRECISION | Global skill estimate           |
| global_sigma     | DOUBLE PRECISION | Global uncertainty              |
| total_matches    | INTEGER          | Total matches across all guilds |
| guilds_played_in | BIGINT[]         | Array of guild IDs              |
| last_updated     | TIMESTAMPTZ      | When last recalculated          |

**Constraints:**

- `uq_global_user_game` UNIQUE (user_id, game_id)
- `chk_global_rating_positive`: global_mu > 0 AND global_sigma > 0
- `chk_global_matches`: total_matches >= 0
- Foreign keys to users, games (ON DELETE CASCADE)

**Indexes:**

- `idx_global_leaderboard` on (game_id, global_mu-3*global_sigma DESC)
- `idx_global_user` on (user_id, game_id)

**Notes:**

- Global ratings combine ratings from all guilds
- Uses Bayesian weighted average
- Recalculated after each rated match

---

#### 11. `game_seasons`

Seasonal competitions with time-bound leaderboards.

| Column        | Type                  | Description                           |
|---------------|-----------------------|---------------------------------------|
| season_id     | SERIAL (PK)           | Unique season identifier              |
| season_name   | VARCHAR(100) NOT NULL | Season name                           |
| game_id       | INTEGER NOT NULL      | Reference to games                    |
| guild_id      | BIGINT                | Reference to guilds (NULL for global) |
| start_date    | TIMESTAMPTZ NOT NULL  | Season start                          |
| end_date      | TIMESTAMPTZ NOT NULL  | Season end                            |
| is_active     | BOOLEAN               | Whether season is active              |
| season_config | JSONB                 | Season-specific configuration         |
| created_at    | TIMESTAMPTZ           | Record creation time                  |

**Constraints:**

- `uq_season_name` UNIQUE (game_id, guild_id, season_name)
- `chk_season_dates`: end_date > start_date
- Foreign keys to games, guilds (ON DELETE CASCADE)

**Indexes:**

- `idx_seasons_active` on (game_id, guild_id, is_active) WHERE is_active = TRUE
- `idx_seasons_dates` on (start_date, end_date)

**Example season_config:**

```json
{
  "min_matches": 10,
  "prizes": [
    "🥇 Champion",
    "🥈 Runner-up",
    "🥉 Third Place"
  ],
  "special_rules": {
    "double_points": true
  }
}
```

---

#### 12. `database_migrations`

Database schema version tracking.

| Column       | Type               | Description                |
|--------------|--------------------|----------------------------|
| migration_id | SERIAL (PK)        | Unique migration ID        |
| version      | VARCHAR(50) UNIQUE | Version number (semver)    |
| description  | TEXT               | Migration description      |
| applied_at   | TIMESTAMPTZ        | When migration was applied |
| checksum     | VARCHAR(64)        | SHA-256 checksum           |

**Constraints:**

- `chk_version_format`: version ~ '^\d+\.\d+(\.\d+)?$'

**Current Version:** 2.5.0 (migrations from 2.4.0)

---

## Views

PlayCord provides 10 views for common query patterns.

### 1. `v_active_leaderboard`

Leaderboard with minimum match requirements and win rates.

**Columns:**

- game_id, user_id, username (global ratings; filter to a guild in application code)
- mu, sigma, conservative_rating (mu - 3*sigma)
- matches_played, wins, losses, draws
- win_rate (calculated)
- last_played

**Filters:**

- Only players with matches_played >= 5
- Ordered by conservative_rating DESC

**Usage:**

```sql
SELECT *
FROM v_active_leaderboard
WHERE game_id = $1
LIMIT 10;
```

---

### 2. `v_recent_activity`

Recent and ongoing matches with player information (last 7 days).

**Columns:**

- match_id, game_name, display_name
- guild_id, status, started_at, ended_at
- player_usernames (array)
- is_rated

**Filters:**

- started_at >= NOW() - INTERVAL '7 days'
- Ordered by started_at DESC

**Usage:**

```sql
SELECT *
FROM v_recent_activity
WHERE guild_id = $1
LIMIT 20;
```

---

### 3. `v_player_stats`

Comprehensive player statistics per game.

**Columns:**

- user_id, guild_id, game_id
- username, game_name
- mu, sigma, conservative_rating
- matches_played, wins, losses, draws
- win_rate, avg_match_duration
- last_played, days_since_last_match

**Usage:**

```sql
SELECT *
FROM v_player_stats
WHERE user_id = $1
  AND guild_id = $2;
```

---

### 4. `v_global_leaderboard`

Global leaderboard across all guilds.

**Columns:**

- user_id, game_id, username, game_name
- global_mu, global_sigma, conservative_rating
- total_matches, guilds_played_in (array)
- last_updated

**Filters:**

- Ordered by conservative_rating DESC

**Usage:**

```sql
SELECT *
FROM v_global_leaderboard
WHERE game_id = $1
LIMIT 100;
```

---

### 5. `v_match_summary`

Detailed match information with participants.

**Columns:**

- match_id, game_name, guild_id
- started_at, ended_at, status, is_rated
- participant_count
- winner_username, winner_ranking
- participants (JSON array with details)

**Usage:**

```sql
SELECT *
FROM v_match_summary
WHERE match_id = $1;
```

---

### 6. `v_user_match_history`

User match history with outcomes and rating changes.

**Columns:**

- user_id, match_id, game_name, guild_id
- started_at, ended_at, is_rated
- final_ranking, score
- mu_before, mu_after, mu_delta
- sigma_before, sigma_after, sigma_delta
- opponent_usernames (array)

**Usage:**

```sql
SELECT *
FROM v_user_match_history
WHERE user_id = $1
  AND guild_id = $2
ORDER BY ended_at DESC
LIMIT 20;
```

---

### 7. `v_inactive_players`

Players inactive for 30+ days (skill decay candidates).

**Columns:**

- user_id, guild_id, game_id, username, game_name
- mu, sigma, conservative_rating
- matches_played, last_played
- days_inactive, last_sigma_increase

**Filters:**

- last_played < NOW() - INTERVAL '30 days'
- Ordered by days_inactive DESC

**Usage:**

```sql
SELECT *
FROM v_inactive_players
WHERE guild_id = $1;
```

---

### 8. `v_guild_activity_summary`

Guild-level activity metrics.

**Columns:**

- guild_id, total_users, active_users_7d, active_users_30d
- total_matches, matches_7d, matches_30d
- games_played (array), most_popular_game
- avg_match_duration_minutes

**Usage:**

```sql
SELECT *
FROM v_guild_activity_summary
WHERE guild_id = $1;
```

---

### 9. `v_game_popularity`

Game popularity metrics across guilds.

**Columns:**

- game_id, game_name, display_name
- total_matches, total_players
- guilds_active_in (count)
- avg_matches_per_day
- last_played

**Filters:**

- Ordered by total_matches DESC

**Usage:**

```sql
SELECT *
FROM v_game_popularity
ORDER BY total_matches DESC;
```

---

### Maintenance Functions

**`apply_skill_decay(days_inactive, sigma_increase_factor)`**

- Increases sigma for inactive players (global `user_game_ratings` rows)
- Returns affected user_id, game_id, old/new sigma, days_since_play

**`cleanup_old_analytics(days_to_keep)`**

- Deletes analytics events older than specified days

### Rating Functions

**Global ratings** live in `user_game_ratings` (migration 2.4.0 removed `global_ratings` and related functions).

---

## PostgreSQL Functions

PlayCord provides 12 PostgreSQL functions for automation and maintenance.

### Rating Functions

#### `calculate_conservative_rating(mu, sigma)`

**Returns:** DOUBLE PRECISION

Calculates conservative rating (mu - 3*sigma) for leaderboard ranking.

**Parameters:**

- `mu`: Skill estimate
- `sigma`: Uncertainty

**Usage:**

```sql
SELECT calculate_conservative_rating(1500.0, 200.0); -- Returns 900.0
```

---

#### `update_global_rating` / `batch_update_global_ratings` (removed)

These functions and the `global_ratings` table were removed in migration **2.4.0**. Global skill is stored in `user_game_ratings` (one row per user per game).

---

### Maintenance Functions

#### `apply_skill_decay(days_inactive, sigma_increase_factor)`

**Returns:** TABLE (user_id, game_id, old_sigma, new_sigma, days_since_play)

Increases sigma (uncertainty) for players inactive beyond threshold, respecting per-game `min_sigma` in `games.rating_config`.

**Parameters:**

- `days_inactive`: Number of days to consider inactive (e.g., 30)
- `sigma_increase_factor`: Applied as `sigma * (1 + factor)` (e.g., `0.1` = 10% increase)

**Usage:**

```sql
-- Increase sigma by 10% for players inactive 30+ days
SELECT *
FROM apply_skill_decay(30, 0.1);
```

**Returns (example):**
| user_id | game_id | old_sigma | new_sigma | days_since_play |
|---------|---------|-----------|-----------|-----------------|
| 123 | 1 | 200.0 | 220.0 | 45 |

---

#### `cleanup_old_analytics(days_to_keep)`

**Returns:** BIGINT (number of deleted events)

Deletes analytics events older than specified days.

**Parameters:**

- `days_to_keep`: Retention period in days

**Usage:**

```sql
-- Delete events older than 90 days
SELECT cleanup_old_analytics(90);
```

---

#### `archive_old_matches(days_old)`

**Returns:** BIGINT (number of archived matches)

Marks completed matches older than specified days as archived (sets metadata.archived = true).

**Parameters:**

- `days_old`: Age threshold in days

**Usage:**

```sql
-- Archive matches completed over 365 days ago
SELECT archive_old_matches(365);
```

---

### Query Functions

#### `get_user_rank(user_id, guild_id, game_id)`

**Returns:** INTEGER (rank position, 1-indexed)

Gets user's current leaderboard rank for a specific game in a guild.

**Parameters:**

- `user_id`: User ID
- `guild_id`: Guild ID
- `game_id`: Game ID

**Usage:**

```sql
SELECT get_user_rank(123456789, 987654321, 1); -- Returns rank (e.g., 5)
```

**Returns:** NULL if user has no rating

---

#### `get_head_to_head_stats(user1_id, user2_id, game_id)`

**Returns:** TABLE (user1_wins, user2_wins, draws, total_matches)

Gets head-to-head statistics between two players for a specific game.

**Parameters:**

- `user1_id`: First user ID
- `user2_id`: Second user ID
- `game_id`: Game ID (NULL for all games)

**Usage:**

```sql
SELECT *
FROM get_head_to_head_stats(123, 456, 1);
```

**Returns:**
| user1_wins | user2_wins | draws | total_matches |
|------------|------------|-------|---------------|
| 5 | 3 | 1 | 9 |

---

#### `get_match_replay_data(match_id)`

**Returns:** TABLE (move_number, user_id, username, move_data, timestamp, time_taken_ms)

Gets all data needed to replay a match move-by-move.

**Parameters:**

- `match_id`: Match ID

**Usage:**

```sql
SELECT *
FROM get_match_replay_data(12345)
ORDER BY move_number;
```

---

#### `get_player_activity_summary(user_id, days)`

**Returns:** TABLE (comprehensive activity stats)

Gets comprehensive activity summary for a player over specified period.

**Parameters:**

- `user_id`: User ID
- `days`: Number of days to analyze

**Returns:**

- total_matches, total_wins, total_losses, total_draws
- games_played (array), guilds_played_in (array)
- avg_match_duration_minutes
- rating_changes (JSON per game)

**Usage:**

```sql
SELECT *
FROM get_player_activity_summary(123456789, 30);
```

---

#### `validate_move_sequence(match_id)`

**Returns:** BOOLEAN

Validates that move sequence has no gaps (all move numbers 1 to N are present).

**Parameters:**

- `match_id`: Match ID

**Usage:**

```sql
SELECT validate_move_sequence(12345); -- Returns TRUE if valid
```

---

### Trigger Functions

#### `prevent_direct_rating_updates()`

**Type:** TRIGGER FUNCTION  
**Purpose:** Prevents manual updates to user_game_ratings table

This trigger prevents direct UPDATE statements on critical rating fields (mu, sigma, matches_played, wins, losses,
draws) to ensure ratings only change through official match completion logic.

**Attached to:** user_game_ratings table (BEFORE UPDATE)

**Exception:** Updates with `current_user = 'playcord_system'` are allowed

---

## TrueSkill Rating System

PlayCord uses the **TrueSkill** rating system developed by Microsoft Research for ranking players.

### Key Concepts

#### Mu (μ) - Skill Estimate

- Represents the estimated "true skill" of a player
- Default starting value: 1000.0
- Higher mu = better player
- Updated after each match based on performance

#### Sigma (σ) - Uncertainty

- Represents uncertainty about the skill estimate
- Default starting value: 333.33
- Lower sigma = more confident in the rating
- Decreases as player plays more matches
- Increases over time for inactive players (skill decay)

#### Conservative Rating

- Formula: `mu - 3*sigma`
- Used for leaderboard ranking
- Accounts for uncertainty (new players start lower despite high mu)
- Example: mu=1500, sigma=200 → conservative=900

### Rating Updates

After each match:

1. Calculate expected performance based on current ratings
2. Compare actual performance to expected
3. Update mu based on surprise factor
4. Update sigma (generally decreases with more matches)
5. Record changes in rating_history table

### Skill Decay

To prevent rating inflation and account for skill deterioration:

- Players inactive 30+ days have sigma increased
- Typical increase: 10% per month
- Does not affect mu, only uncertainty
- Managed by `apply_skill_decay()` function

### Configuration

Each game has TrueSkill parameters in `games.rating_config`:

```json
{
  "sigma": 0.1667,
  // Uncertainty factor
  "beta": 0.0833,
  // Skill difference factor
  "tau": 0.01,
  // Dynamics factor (skill change over time)
  "draw": 0.9
  // Draw probability threshold
}
```

---

## Common Query Patterns

### Get Guild Leaderboard

```sql
SELECT *
FROM v_active_leaderboard
WHERE guild_id = $1
  AND game_id = $2
ORDER BY conservative_rating DESC
LIMIT 10;
```

### Get User Match History

```sql
SELECT *
FROM v_user_match_history
WHERE user_id = $1
  AND guild_id = $2
ORDER BY ended_at DESC
LIMIT 10;
```

### Get Player Stats for a Game

```sql
SELECT username,
       mu,
       sigma,
       calculate_conservative_rating(mu, sigma)           as rating,
       matches_played,
       wins,
       losses,
       draws,
       ROUND(100.0 * wins / NULLIF(matches_played, 0), 1) as win_rate
FROM user_game_ratings ugr
         JOIN users u ON ugr.user_id = u.user_id
WHERE ugr.user_id = $1
  AND ugr.guild_id = $2
  AND ugr.game_id = $3;
```

### Get Recent Matches in a Guild

```sql
SELECT *
FROM v_recent_activity
WHERE guild_id = $1
ORDER BY started_at DESC
LIMIT 20;
```

### Get Head-to-Head Stats

```sql
SELECT *
FROM get_head_to_head_stats($user1_id, $user2_id, $game_id);
```

### Get Match Replay Data

```sql
SELECT move_number,
       username,
       move_data,
       timestamp,
       time_taken_ms
FROM get_match_replay_data($match_id)
ORDER BY move_number;
```

### Get User's Current Rank

```sql
SELECT get_user_rank($user_id, $guild_id, $game_id) as rank;
```

### Get Rating History for Chart

```sql
SELECT timestamp,
       mu_after                                             as mu,
       sigma_after                                          as sigma,
       calculate_conservative_rating(mu_after, sigma_after) as rating
FROM rating_history
WHERE user_id = $1
  AND guild_id = $2
  AND game_id = $3
ORDER BY timestamp ASC;
```

### Get Game Popularity

```sql
SELECT *
FROM v_game_popularity
ORDER BY total_matches DESC;
```

### Get Inactive Players for Skill Decay

```sql
SELECT *
FROM v_inactive_players
WHERE guild_id = $1
  AND days_inactive >= 30;
```

### Get Guild Activity Summary

```sql
SELECT *
FROM v_guild_activity_summary
WHERE guild_id = $1;
```

---

## Performance Optimization

### Indexes

All critical queries are covered by indexes for optimal performance:

**Leaderboard Queries:**

- `idx_rating_leaderboard` on (guild_id, game_id, mu-3*sigma DESC)
- Target: < 50ms for 10k+ users

**Match History:**

- `idx_participants_user` on (user_id, match_id DESC)
- `idx_matches_recent` on (ended_at DESC)
- Target: < 20ms

**Move Retrieval:**

- `idx_moves_match_sequence` on (match_id, move_number ASC)
- Target: < 10ms

**Analytics:**

- `idx_analytics_type_time` on (event_type, timestamp DESC)
- `idx_analytics_guild` on (guild_id, timestamp DESC)

**Global Ratings:**

- `idx_global_leaderboard` on (game_id, global_mu-3*global_sigma DESC)

### Connection Pooling

Default configuration in `config.yaml`:

- **Pool size:** 10 connections (concurrent queries)
- **Max overflow:** 20 connections (burst capacity)
- **Timeout:** 30 seconds (wait for available connection)

Adjust based on load:

```yaml
db:
  pool_size: 20      # Increase for high traffic
  max_overflow: 40   # Increase for burst handling
  pool_timeout: 30   # Decrease if connections available
```

### Query Optimization Tips

1. **Use views for complex queries** - Pre-optimized with proper joins
2. **Filter early** - WHERE clauses before JOINs when possible
3. **Limit result sets** - Always use LIMIT for paginated data
4. **Index foreign keys** - All FK columns are indexed
5. **JSONB queries** - Use GIN indexes for frequent JSONB lookups
6. **Avoid SELECT \*** - Specify needed columns in production

### Monitoring Performance

```sql
-- Show slow queries (>100ms)
SELECT query, mean_exec_time, calls
FROM pg_stat_statements
WHERE mean_exec_time > 100
ORDER BY mean_exec_time DESC
LIMIT 10;

-- Show table sizes
SELECT schemaname,
       tablename,
       pg_size_pretty(pg_total_relation_size(schemaname || '.' || tablename)) AS size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname || '.' || tablename) DESC;

-- Show index usage
SELECT schemaname,
       tablename,
       indexname,
       idx_scan,
       idx_tup_read,
       idx_tup_fetch
FROM pg_stat_user_indexes
WHERE schemaname = 'public'
ORDER BY idx_scan DESC;
```
