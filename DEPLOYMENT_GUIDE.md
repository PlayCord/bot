# Database Fixes - Deployment Guide

## Overview

This guide explains how the critical database fixes are deployed and verified.

## Automatic Deployment

When the PlayCord bot starts and the database connection is initialized, all pending migrations are automatically applied:

```python
# In playcord/utils/database.py initialization:
from playcord.utils import db_migrations
db_migrations.apply_migrations(database)
```

The migration system:
1. Checks the `database_migrations` table for applied versions
2. Runs any migrations not yet applied (in version order)
3. Records each migration with timestamp and checksum for audit trail

## Migration Execution Order

Migrations execute in strict version order:

1. **1.1.0** - Backfill sigma < 0.001 values
   - Duration: <1 second for typical data
   - Data impact: Modifies existing ratings

2. **1.1.1** - Add ended_at constraint + backfill
   - Duration: <1 second for typical data
   - Data impact: Backfills missing ended_at timestamps

3. **1.1.2** - Create ranking validation trigger
   - Duration: <1 second
   - Data impact: No data changes, adds database function

4. **1.1.3** - Add is_deleted columns and indexes
   - Duration: 1-5 seconds depending on table size
   - Data impact: Adds 5 new columns (5 bytes per row)
   - Creates 5 indexes (may take longer on large tables)

5. **1.1.4** - Update FK constraints
   - Duration: 1-2 seconds
   - Data impact: No data changes, updates constraints

**Total expected time:** <20 seconds for typical data

## Database Verification

After migrations complete, verify constraints are in place:

```sql
-- Verify CHECK constraints exist
SELECT constraint_name, constraint_type
FROM information_schema.table_constraints
WHERE table_name IN ('user_game_ratings', 'matches')
AND constraint_type = 'CHECK';

-- Expected output:
-- chk_rating_floor | CHECK
-- chk_completed_match_has_end_time | CHECK

-- Verify trigger exists
SELECT trigger_name, event_object_table
FROM information_schema.triggers
WHERE trigger_name = 'trg_validate_completed_match_rankings';

-- Expected output:
-- trg_validate_completed_match_rankings | matches

-- Verify is_deleted columns exist
SELECT table_name, column_name
FROM information_schema.columns
WHERE column_name = 'is_deleted'
ORDER BY table_name;

-- Expected output:
-- users | is_deleted
-- user_game_ratings | is_deleted
-- match_participants | is_deleted
-- match_moves | is_deleted
-- rating_history | is_deleted
```

## Application-Level Changes

No application code changes are required for deployment. The changes are:

1. **Backward Compatible:** Existing queries continue to work
2. **Additive:** New WHERE clauses are added to queries (not replacing)
3. **Transparent:** Soft-deleted data is hidden from queries automatically
4. **Safe:** All changes have default values and idempotent migrations

## Testing Before Deployment

### Manual Testing
```sql
-- Test sigma constraint (should fail):
INSERT INTO user_game_ratings (user_id, game_id, mu, sigma)
VALUES (999, 1, 1500, 0.0001);
-- Expected: CONSTRAINT CHECK violation

-- Test ended_at constraint (should fail):
UPDATE matches SET status = 'completed', ended_at = NULL
WHERE match_id = 1;
-- Expected: CONSTRAINT CHECK violation

-- Test ranking trigger (should fail):
UPDATE matches SET status = 'completed'
WHERE match_id = (SELECT match_id FROM match_participants 
                  WHERE final_ranking IS NULL LIMIT 1);
-- Expected: Custom error message about missing rankings
```

### Automated Testing
```bash
# Run any existing tests
cd /Users/jjreder/PlayCord/pythonProject
python -m pytest

# Verify migrations load
python -c "from playcord.utils.db_migrations import MIGRATIONS; print(f'Loaded {len(MIGRATIONS)} migrations')"

# Verify database methods exist
python -c "from playcord.utils.database import Database; print('Methods:', [m for m in dir(Database) if 'delete' in m or 'restore' in m or 'archive' in m])"
```

## Rollback Procedure

**Important:** Migrations are designed to be irreversible by default. However, rollback can be done:

### For Migration 1.1.0 (Sigma backfill)
No direct rollback needed - just backfill again if needed:
```sql
UPDATE user_game_ratings SET sigma = 0.001 WHERE sigma < 0.001;
```

### For Migration 1.1.1 (ended_at constraint)
The constraint cannot be dropped while the CHECK is active. To rollback:
```sql
ALTER TABLE matches DROP CONSTRAINT chk_completed_match_has_end_time;
```

### For Migration 1.1.2 (Ranking trigger)
```sql
DROP TRIGGER trg_validate_completed_match_rankings ON matches;
DROP FUNCTION validate_completed_match_rankings();
```

### For Migration 1.1.3 (is_deleted columns)
Columns can be dropped (data loss):
```sql
ALTER TABLE users DROP COLUMN is_deleted;
-- ... repeat for other tables
```

### For Migration 1.1.4 (FK constraints)
```sql
ALTER TABLE user_game_ratings DROP CONSTRAINT fk_user_rating_user;
ALTER TABLE user_game_ratings ADD CONSTRAINT fk_user_rating_user
    FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE;
-- ... repeat for other tables
```

## Performance Monitoring

Monitor these metrics after deployment:

### Query Performance
```sql
-- Check if is_deleted indexes are being used
EXPLAIN ANALYZE SELECT * FROM users WHERE is_deleted = FALSE;
-- Look for "Index Scan" on idx_users_deleted
```

### Storage
```sql
-- Check table sizes (should add ~5 bytes per row)
SELECT 
    table_name,
    pg_size_pretty(pg_total_relation_size(quote_ident(table_name)))
FROM information_schema.tables
WHERE table_schema = 'public'
ORDER BY pg_total_relation_size(quote_ident(table_name)) DESC;
```

### Constraint Violations
```sql
-- Monitor for constraint violations
SELECT * FROM database_migrations 
ORDER BY applied_at DESC LIMIT 5;
```

## Operational Impact

### Downtime
- **Expected:** None - migrations run during startup
- **Risk:** Very low - all migrations are safe (backfill, trigger, constraint additions)

### Data Loss
- **Expected:** None - all changes preserve data
- **User-facing changes:** Deleted users hidden from queries (soft delete)

### Performance Impact
- **Query impact:** Negligible (indexed WHERE clauses)
- **Storage impact:** ~5 bytes per row per table (minimal)
- **Index impact:** 5 new indexes (minimal size, high efficiency)

## Recovery Procedures

### If migrations fail at startup:
1. Check error message in logs
2. Verify database connectivity
3. Manually rollback (see Rollback Procedure above)
4. Fix root cause
5. Re-run migrations

### If constraints are too strict:
1. Backfill data using migration SQL
2. Verify data conforms to constraints
3. Try again

### If performance degrades:
1. Check index usage (EXPLAIN ANALYZE)
2. Rebuild indexes if fragmented: `REINDEX TABLE table_name;`
3. Run ANALYZE to update statistics

## Validation Checklist

Before declaring deployment complete:

- [ ] All 5 migrations applied (check `database_migrations` table)
- [ ] Constraints visible in information_schema
- [ ] Trigger function exists and is attached
- [ ] is_deleted columns exist on all 5 tables
- [ ] is_deleted indexes created
- [ ] Query performance is acceptable (no regression)
- [ ] Soft-deleted users are hidden from queries
- [ ] delete_user() performs UPDATE (not DELETE)
- [ ] restore_user() successfully re-activates deleted users
- [ ] archive_user() reports correct counts

## Monitoring After Deployment

### Key Metrics to Watch

1. **Migration Execution Time:** Should complete in <20 seconds
2. **Query Performance:** No degradation expected
3. **Constraint Violations:** Should be zero (if so, data issue exists)
4. **Soft-Delete Usage:** Monitor count of is_deleted = TRUE records
5. **FK Cascade Changes:** User deletion should no longer cascade

## Support

If issues occur during deployment:

1. Check logs for specific error messages
2. Verify database connectivity and permissions
3. Check migration SQL syntax
4. Verify table/column/index names exist
5. Contact database administrator if needed

## Summary

All database fixes are deployed automatically via idempotent migrations during application startup. No manual intervention required under normal circumstances. The fixes improve data integrity without breaking existing functionality or causing downtime.

