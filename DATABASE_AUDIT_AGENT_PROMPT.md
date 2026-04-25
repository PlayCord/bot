# Database Audit & Improvements Agent Prompt

## Objective
Design and implement enhanced database audit and tracking capabilities for PlayCord that address identified schema gaps while maintaining referential integrity and query performance.

---

## Context

The PlayCord database (PostgreSQL) tracks Discord game matches with TrueSkill ratings, move histories, and analytics. Current schema analysis identified **10 issues** spanning data integrity, performance, and consistency. This prompt defines requirements for:

1. **Audit trail infrastructure** – Immutable tracking of all data changes
2. **History mechanism consolidation** – Unified rating/event history
3. **Constraint enforcement** – Database-level validation of business rules
4. **Performance optimization** – Strategic indexing and materialization

---

## Current State Issues (Reference)

### Critical Issues
- **TrueSkill defaults inconsistency:** Column defaults (1500/166.67) vs. per-game `rating_config` min values
- **Missing index:** `match_participants` lacks compound index for (match_id, final_ranking, user_id)
- **Lost attribution:** `replay_events.actor_user_id` allows NULL with no audit mechanism

### Medium Issues
- **Dual history:** `match_participants.mu_before/sigma_before` vs. `rating_history` table (redundant)
- **View performance:** `v_match_outcomes` recomputes GROUP BY on every query
- **match_code case sensitivity:** Two indices, duplicates possible via case variation
- **No soft-delete:** `match_moves` cascade-deleted; no archive or recovery
- **Missing constraints:** `final_ranking` nullable for completed matches

---

## Requirements: What to Store & Retrieve

### 1. **Immutable Audit Log**

**Table: `audit_log` (NEW)**

Store every material data change for compliance, debugging, and recovery.

**Must store:**
- `audit_id` (BIGSERIAL PK)
- `timestamp` (TIMESTAMPTZ) – When change occurred
- `actor_user_id` (BIGINT, nullable) – User who triggered change (NULL if system)
- `operation_type` (VARCHAR) – INSERT, UPDATE, DELETE, SYSTEM_EVENT
- `table_name` (VARCHAR) – Target table (e.g., "user_game_ratings")
- `record_id` (BIGINT, nullable) – PK of affected row
- `before_state` (JSONB) – Full row snapshot before change (for UPDATE/DELETE)
- `after_state` (JSONB) – Full row snapshot after change (for INSERT/UPDATE)
- `change_reason` (TEXT, nullable) – Why change occurred (e.g., "skill_decay", "rating_update", "user_delete_request")
- `session_id` (VARCHAR, nullable) – Trace to source session/transaction
- `metadata` (JSONB) – Additional context (e.g., {"ip": "...", "api_version": "..."})

**Must retrieve:**
- Full change history for a specific record (SELECT * WHERE table_name = 'X' AND record_id = Y ORDER BY timestamp DESC)
- All changes by actor in date range (SELECT * WHERE actor_user_id = Z AND timestamp > NOW() - INTERVAL '30 days')
- Rollback candidate audit entries (to support "undo" logic)
- Change frequency metrics (anomaly detection: sudden spike in DELETE operations)

**Performance:** Index on (table_name, record_id, timestamp DESC) for reverse chronological lookup

---

### 2. **Unified Rating History**

**Consolidate:** `match_participants.mu_before/sigma_before/mu_delta/sigma_delta` + `rating_history`

**Requirement:** Single canonical source of truth for rating changes

**Table: `rating_change_log` (REPLACES/AUGMENTS rating_history)**

**Must store:**
- `change_id` (BIGSERIAL PK)
- `user_id` (BIGINT) – Player whose rating changed
- `game_id` (INTEGER) – Which game
- `match_id` (BIGINT, nullable) – Match trigger (NULL if system event like decay)
- `change_type` (VARCHAR) – 'match_result', 'skill_decay', 'admin_adjustment', 'system_reset'
- `mu_before`, `sigma_before` (DOUBLE PRECISION)
- `mu_after`, `sigma_after` (DOUBLE PRECISION)
- `confidence_delta` (DOUBLE PRECISION, nullable) – Derived from sigma change
- `is_system_generated` (BOOLEAN) – True for auto-decay, False for match results
- `triggered_by_user_id` (BIGINT, nullable) – Admin who forced update (NULL if auto)
- `created_at` (TIMESTAMPTZ)

**Must retrieve:**
- Player rating progression over time (all changes for user/game in date range)
- Last N rating changes for a player
- Rating changes for a specific match (all participants)
- System-generated changes vs. match-driven changes (for anomaly detection)
- Rating change audit (who changed what, when, why)

**Performance:** Indices on (user_id, game_id, created_at DESC), (match_id), (change_type, created_at DESC)

---

### 3. **Replay Event Attribution & Auditing**

**Table: `replay_events` (ENHANCE)**

**Current gap:** `actor_user_id` nullable; no tracking of who initiated the replay event

**Must store (enhancements):**
- `replay_event_id` (BIGSERIAL PK) – Already exists as event_id
- `match_id` (BIGINT FK) – Already exists
- `sequence_number` (INTEGER) – Already exists
- `event_type` (VARCHAR) – Already exists ('move', 'forfeit', 'system_reset', etc.)
- `actor_user_id` (BIGINT FK) – **Actor responsible** (user_id if player action, NULL for auto-system)
- `actor_type` (VARCHAR) – **NEW: 'player', 'admin', 'system'** (clarifies NULL case)
- `payload` (JSONB) – Already exists
- `is_reverifiable` (BOOLEAN) – **NEW: True if event can be undone**
- `reversal_event_id` (BIGINT FK, nullable) – **NEW: Links to reversal event if undone**
- `created_at` (TIMESTAMPTZ) – Already exists
- `audit_log_id` (BIGINT FK, nullable) – **NEW: Links to audit_log for full context**

**Must retrieve:**
- All events in a match replay (match_id, ordered by sequence_number)
- Events by specific actor (actor_user_id = X) – for user action auditing
- Undone events (WHERE reversal_event_id IS NOT NULL) – for recovery
- Events without clear attribution (actor_type = 'system', actor_user_id IS NULL) – for investigation
- Reversible events in a match (for appeal/dispute resolution)

**Constraint:** `actor_user_id IS NOT NULL OR actor_type = 'system'` – Either link to user or mark as system

---

### 4. **Match Completion State Validation**

**Table: `match_participants` (ADD CONSTRAINTS)**

**Current gap:** `final_ranking` nullable even for completed matches

**Must store:**
- Add CHECK constraint:
  ```sql
  CHECK (
    final_ranking IS NOT NULL 
    OR (SELECT status FROM matches WHERE match_id = match_participants.match_id) != 'completed'
  )
  ```
  *OR create trigger to enforce at insert/match status change*

**Must retrieve:**
- Matches with incomplete rankings (for QA/repair)
- Participants with NULL final_ranking in completed matches (data quality report)
- Inconsistent states for alerting

---

### 5. **Soft-Delete & Archive System**

**Table: `match_moves` (ADD SOFT-DELETE)**

**Current gap:** Cascade-deleted with no recovery mechanism

**Must store (enhancements):**
- Add columns to `match_moves`:
  - `is_deleted` (BOOLEAN DEFAULT FALSE)
  - `deleted_at` (TIMESTAMPTZ, nullable)
  - `deleted_by_user_id` (BIGINT FK, nullable) – Admin or system that deleted
  - `deletion_reason` (TEXT, nullable) – Why deleted (e.g., "match_abandoned", "dispute_resolution")

**Create table: `match_moves_archive`**
- Identical schema to `match_moves`
- Stores hard-deleted records for long-term recovery
- Retention policy: Keep for 1 year minimum

**Triggers needed:**
- When `match_moves.is_deleted = TRUE`: Soft-delete the row
- On hard-delete: Copy to `match_moves_archive` before deletion
- Prevent deletion of `match_moves` for matches still in `matches` table (enforce via trigger)

**Must retrieve:**
- All moves for a match including soft-deleted (add WHERE is_deleted = FALSE to queries)
- Deleted moves for investigation (WHERE is_deleted = TRUE)
- Full archived move history (from `match_moves_archive`)
- Who deleted what and when (deleted_at, deleted_by_user_id, deletion_reason)

---

### 6. **Performance Optimization: Materialized Metrics**

**Table: `match_outcome_cache` (NEW MATERIALIZED VIEW)**

**Purpose:** Pre-compute expensive aggregations from `v_match_outcomes` to avoid repeated GROUP BY

**Must store:**
- `cache_id` (BIGSERIAL PK)
- `user_id` (BIGINT)
- `game_id` (INTEGER)
- `wins` (INTEGER)
- `losses` (INTEGER)
- `draws` (INTEGER)
- `cached_at` (TIMESTAMPTZ)
- `is_current` (BOOLEAN) – Staleness flag

**Must retrieve:**
- Cached outcome totals for a user/game (instant lookup instead of GROUP BY)
- Staleness: Which caches need refresh (is_current = FALSE)
- Time-based freshness: Cache older than 1 hour

**Refresh strategy:**
- Trigger on `match_participants` INSERT/UPDATE (after match completion)
- Batch refresh every 30 minutes
- Manual refresh endpoint for admin

---

### 7. **Index Optimization**

**Indices to add:**
- `CREATE INDEX idx_participants_outcome ON match_participants(match_id, final_ranking, user_id)`
- `CREATE INDEX idx_replay_events_actor_type ON replay_events(actor_type, created_at DESC) WHERE actor_type != 'system'`
- `CREATE INDEX idx_audit_log_table_record ON audit_log(table_name, record_id, timestamp DESC)`
- `CREATE INDEX idx_audit_log_actor ON audit_log(actor_user_id, timestamp DESC) WHERE actor_user_id IS NOT NULL`
- `CREATE INDEX idx_rating_change_type ON rating_change_log(change_type, created_at DESC)`
- `CREATE INDEX idx_match_moves_deleted ON match_moves(match_id, is_deleted) WHERE is_deleted = FALSE`

---

### 8. **Constraint Enforcement Table**

**Table: `data_quality_checks` (NEW)**

Track validation rules and failures for continuous monitoring

**Must store:**
- `check_id` (BIGSERIAL PK)
- `check_name` (VARCHAR) – e.g., "final_ranking_not_null", "tru_eskill_default_consistency"
- `check_query` (TEXT) – SQL to find violations
- `last_run_at` (TIMESTAMPTZ)
- `violations_found` (INTEGER)
- `is_critical` (BOOLEAN)
- `auto_fix_available` (BOOLEAN)

**Must retrieve:**
- Failed checks (violations_found > 0)
- Check execution history (for trend analysis)
- Critical checks vs. warnings (for alerting priority)

---

## Implementation Deliverables

1. **SQL migration script** (follow existing pattern in `db_migrations.py`)
   - Create audit_log table
   - Create/consolidate rating_change_log
   - Enhance replay_events table
   - Add soft-delete columns to match_moves
   - Create archive table
   - Create materialized cache tables
   - Add indices
   - Add CHECK constraints

2. **Trigger functions** (in `functions.sql`)
   - `audit_log_insert_trigger()` – Capture all INSERT/UPDATE/DELETE
   - `replay_event_attribution_trigger()` – Validate actor_user_id vs. actor_type
   - `match_completion_trigger()` – Enforce final_ranking on status='completed'
   - `soft_delete_trigger()` – Handle is_deleted flag
   - `cache_invalidation_trigger()` – Mark cache stale on rating change

3. **Views** (in `views.sql`)
   - `v_recent_audit_log` – Last 1000 audit entries with actor details
   - `v_rating_progression` – User rating over time from consolidated log
   - `v_match_replay_with_attribution` – Replay events + actor info
   - `v_data_quality_dashboard` – Overview of constraint violations
   - `v_soft_deleted_matches` – Matches with soft-deleted moves

4. **Documentation**
   - ERD showing audit/history relationships
   - Data retention policy (audit logs: 3 years, archives: 1 year, cache: 30 min)
   - Audit trail usage guide (how to query for compliance, recovery)
   - Constraint enforcement rules

5. **Testing**
   - Verify audit log captures all mutations
   - Verify replays correctly attribute events
   - Verify soft-delete doesn't break queries
   - Verify cache refresh performance
   - Data quality check coverage

---

## Success Criteria

✅ Audit log captures 100% of material changes with actor/reason  
✅ No data loss on cascade (soft-delete + archive pattern)  
✅ Rating history single source of truth (no duplication)  
✅ Replay event attribution unambiguous (actor_user_id or actor_type)  
✅ Performance: Leaderboard queries < 200ms (via materialized cache)  
✅ Constraint violations detected via data_quality_checks  
✅ Rollback/recovery possible from audit log + archive tables  

---

## Agent Notes

- Preserve backward compatibility; don't break existing code that reads `match_participants.mu_before`
- Use PostgreSQL-specific features (JSONB, composite indices, IMMUTABLE functions) where beneficial
- Follow existing migration versioning pattern (semantic versioning 1.0.x)
- Add comprehensive comments on all new tables/functions
- Provide sample queries for common audit use cases (e.g., "replay match reconstruction", "player rating dispute resolution")
