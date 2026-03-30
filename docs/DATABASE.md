# PlayCord Database Documentation

## Overview

PlayCord uses **PostgreSQL 14+** (recommended: 16) for persistent storage of game data, user ratings, match history, and analytics. The database is designed for:

- **Extensibility**: Easy to add new games and features
- **Data Integrity**: Comprehensive constraints and foreign keys
- **Performance**: Strategic indexes for common queries
- **Auditability**: Full move history and rating changes
- **Scalability**: Connection pooling and optimized queries

## Architecture

### Database Schema Version: 2.0

The schema consists of:
- **12 core tables** for data storage
- **9 views** for common query patterns
- **15+ PostgreSQL functions** for automation and maintenance
- **25+ indexes** for query optimization
- **20+ constraints** for data validation

## Table Reference

### Core Tables

#### 1. `guilds`
Discord servers where the bot is installed.

| Column | Type | Description |
|--------|------|-------------|
| guild_id | BIGINT (PK) | Discord guild/server ID |
| joined_at | TIMESTAMPTZ | When bot joined the guild |
| settings | JSONB | Guild preferences and configuration |
| is_active | BOOLEAN | Whether guild is active |
| created_at | TIMESTAMPTZ | Record creation time |
| updated_at | TIMESTAMPTZ | Last update time |

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

For full documentation, see the complete schema in `database/schema.sql`.

## PostgreSQL Functions

### Maintenance Functions

**`apply_skill_decay(days_inactive, sigma_increase_factor)`**
- Increases sigma for inactive players
- Returns affected users

**`cleanup_old_analytics(days_to_keep)`**
- Deletes analytics events older than specified days

### Rating Functions

**`update_global_rating(user_id, game_id)`**
- Recalculates global rating using Bayesian combination

## Common Query Patterns

### Get Guild Leaderboard

```sql
SELECT * FROM v_active_leaderboard
WHERE guild_id = $1 AND game_id = $2
ORDER BY conservative_rating DESC
LIMIT 10;
```

### Get User Match History

```sql
SELECT * FROM v_user_match_history
WHERE user_id = $1 AND guild_id = $2
ORDER BY ended_at DESC
LIMIT 10;
```

## Performance Optimization

### Indexes

All critical queries are covered by indexes:
- Leaderboard queries: < 50ms for 10k+ users
- Match history: < 20ms
- Move retrieval: < 10ms

### Connection Pooling

Default configuration:
- Pool size: 10 connections
- Max overflow: 20 connections
- Timeout: 30 seconds

## Backup and Recovery

### Automated Backups

```bash
# Daily backup
pg_dump -U playcord playcord | gzip > backup_$(date +%Y%m%d).sql.gz
```

## Support

For detailed schema information, see `database/schema.sql`, `database/views.sql`, and `database/functions.sql`.
