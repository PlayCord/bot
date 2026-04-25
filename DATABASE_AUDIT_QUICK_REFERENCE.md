# Quick Reference: Database Audit Requirements

## Problem Statement
PlayCord database has 10 schema issues:
- **3 HIGH:** Missing indices, attribute loss, defaults inconsistency
- **5 MEDIUM:** Redundant history, view performance, soft-delete gaps
- **2 LOW:** NULL constraints, documentation

## 8 Core Requirements

| # | Requirement | Problem | Solution |
|---|-------------|---------|----------|
| 1 | **Audit Log** | No immutable change tracking | Create `audit_log` table with full state snapshots |
| 2 | **Rating History** | Dual mechanisms (match_participants + rating_history) | Consolidate into `rating_change_log` |
| 3 | **Replay Attribution** | `actor_user_id` NULL without context | Add `actor_type` enum + constraint |
| 4 | **Soft-Delete** | Cascade data loss | Add `is_deleted`, `deleted_at`, `deleted_by_user_id` to `match_moves` |
| 5 | **Archive** | No recovery mechanism | Create `match_moves_archive` table |
| 6 | **Constraint Enforcement** | `final_ranking` NULL for completed matches | Add trigger + CHECK constraint |
| 7 | **Performance** | `v_match_outcomes` recomputes on every query | Create `match_outcome_cache` materialized view |
| 8 | **Data Quality** | No continuous validation | Create `data_quality_checks` table + monitoring |

## New Tables to Create

```sql
-- 1. Immutable audit trail
audit_log (
  audit_id BIGSERIAL PK,
  timestamp TIMESTAMPTZ,
  actor_user_id BIGINT (nullable),
  operation_type VARCHAR (INSERT/UPDATE/DELETE/SYSTEM_EVENT),
  table_name VARCHAR,
  record_id BIGINT (nullable),
  before_state JSONB,
  after_state JSONB,
  change_reason TEXT (nullable),
  session_id VARCHAR (nullable),
  metadata JSONB
)
INDEX: (table_name, record_id, timestamp DESC)
INDEX: (actor_user_id, timestamp DESC) WHERE actor_user_id IS NOT NULL

-- 2. Consolidated rating history
rating_change_log (
  change_id BIGSERIAL PK,
  user_id BIGINT,
  game_id INTEGER,
  match_id BIGINT (nullable),
  change_type VARCHAR (match_result/skill_decay/admin_adjustment/system_reset),
  mu_before, mu_after DOUBLE PRECISION,
  sigma_before, sigma_after DOUBLE PRECISION,
  confidence_delta DOUBLE PRECISION (nullable),
  is_system_generated BOOLEAN,
  triggered_by_user_id BIGINT (nullable),
  created_at TIMESTAMPTZ
)
INDEX: (user_id, game_id, created_at DESC)
INDEX: (match_id)
INDEX: (change_type, created_at DESC)

-- 3. Archive for deleted moves
match_moves_archive (
  -- Same schema as match_moves
)

-- 4. Performance cache
match_outcome_cache (
  cache_id BIGSERIAL PK,
  user_id BIGINT,
  game_id INTEGER,
  wins INTEGER,
  losses INTEGER,
  draws INTEGER,
  cached_at TIMESTAMPTZ,
  is_current BOOLEAN
)
INDEX: (user_id, game_id)
INDEX: (is_current, cached_at) WHERE NOT is_current

-- 5. Data quality monitoring
data_quality_checks (
  check_id BIGSERIAL PK,
  check_name VARCHAR,
  check_query TEXT,
  last_run_at TIMESTAMPTZ,
  violations_found INTEGER,
  is_critical BOOLEAN,
  auto_fix_available BOOLEAN
)
```

## Enhancements to Existing Tables

### `replay_events` - Add columns:
```sql
actor_type VARCHAR (player/admin/system)  -- Clarifies NULL actor_user_id
is_reverifiable BOOLEAN
reversal_event_id BIGINT FK (nullable)
audit_log_id BIGINT FK (nullable)

-- Add constraint:
CHECK (actor_user_id IS NOT NULL OR actor_type = 'system')
```

### `match_moves` - Add columns:
```sql
is_deleted BOOLEAN DEFAULT FALSE
deleted_at TIMESTAMPTZ (nullable)
deleted_by_user_id BIGINT FK (nullable)
deletion_reason TEXT (nullable)

-- Add index:
CREATE INDEX idx_match_moves_deleted ON match_moves(match_id, is_deleted) WHERE is_deleted = FALSE
```

### `match_participants` - Add constraint:
```sql
-- Via trigger or CHECK:
final_ranking NOT NULL OR (SELECT status FROM matches...) != 'completed'
```

## Triggers to Create

| Trigger Name | On Table | Event | Purpose |
|--------------|----------|-------|---------|
| `audit_log_insert` | All mutable tables | INSERT/UPDATE/DELETE | Capture change |
| `replay_event_attribution` | `replay_events` | INSERT | Validate actor_type/actor_user_id |
| `match_completion` | `matches` | UPDATE (status → 'completed') | Enforce final_ranking NOT NULL |
| `soft_delete` | `match_moves` | UPDATE (is_deleted → TRUE) | Copy to archive, invalidate cache |
| `cache_invalidation` | `user_game_ratings` | UPDATE (mu/sigma) | Mark match_outcome_cache stale |

## Views to Create

| View | Purpose |
|------|---------|
| `v_recent_audit_log` | Last 1000 audit entries with actor details |
| `v_rating_progression` | User rating history over time |
| `v_match_replay_with_attribution` | Replay events + actor info |
| `v_data_quality_dashboard` | Constraint violations overview |
| `v_soft_deleted_matches` | Matches with deleted moves (recovery view) |

## Indices to Add

```sql
-- Leaderboard queries
CREATE INDEX idx_participants_outcome ON match_participants(match_id, final_ranking, user_id)

-- Replay audit trail
CREATE INDEX idx_replay_events_actor_type ON replay_events(actor_type, created_at DESC)

-- Audit log queries
CREATE INDEX idx_audit_log_table_record ON audit_log(table_name, record_id, timestamp DESC)
CREATE INDEX idx_audit_log_actor ON audit_log(actor_user_id, timestamp DESC) WHERE actor_user_id IS NOT NULL

-- Soft-delete optimization
CREATE INDEX idx_match_moves_deleted ON match_moves(match_id, is_deleted) WHERE is_deleted = FALSE

-- Cache lookup
CREATE INDEX idx_match_outcome_cache ON match_outcome_cache(user_id, game_id)
```

## Data Retention Policy

| Data | Retention | Purpose |
|------|-----------|---------|
| `audit_log` | 3 years | Compliance, tax, dispute resolution |
| `rating_change_log` | Indefinite | Historical ratings, skill tracking |
| `match_moves_archive` | 1 year | Soft-delete recovery, appeals |
| `match_outcome_cache` | 30 minutes | Performance optimization |
| `data_quality_checks` | 90 days | Monitoring history |

## Sample Queries (Agent Must Provide)

```sql
-- Replay match reconstruction (with audit)
SELECT * FROM replay_events WHERE match_id = X ORDER BY sequence_number ASC;

-- Player rating dispute resolution
SELECT * FROM rating_change_log WHERE user_id = Y AND game_id = Z ORDER BY created_at DESC;

-- Soft-deleted moves recovery
SELECT * FROM match_moves WHERE is_deleted = TRUE AND match_id = X;

-- Full audit trail for specific record
SELECT * FROM audit_log WHERE table_name = 'matches' AND record_id = M ORDER BY timestamp DESC;

-- Data quality violations
SELECT * FROM data_quality_checks WHERE violations_found > 0 AND is_critical = TRUE;

-- Cache staleness check
SELECT * FROM match_outcome_cache WHERE is_current = FALSE;
```

## Migration Pattern

New migration should follow existing pattern:
- Version: `1.0.5` (increment from current 1.0.4)
- Location: Add to `MIGRATIONS` list in `playcord/utils/db_migrations.py`
- SQL: Staged statements in tuple, numbered sequentially
- Idempotent: All DDL wrapped with `IF NOT EXISTS` / `IF EXISTS`
- Tested: Run against existing production-like schema

---

**Files to Modify/Create:**
- `playcord/infrastructure/db/sql/schema.sql` – Or create separate migration file
- `playcord/infrastructure/db/sql/functions.sql` – Add triggers
- `playcord/infrastructure/db/sql/views.sql` – Add new views
- `playcord/utils/db_migrations.py` – Register migration
- Documentation (design doc, query guide, retention policy)
- Tests (SQL tests, trigger verification, cache performance)
