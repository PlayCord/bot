# Database Audit & Improvements - Requirements Specification

**Version:** 1.0  
**Date:** 2026-04-25  
**Status:** Ready for Implementation

---

## Executive Summary

PlayCord database requires enhanced audit, constraint enforcement, and performance capabilities to address 10 identified
schema issues. This document specifies **WHAT** needs to be built (requirements), not HOW to build it (implementation).

---

## Background & Context

### Current State

- PlayCord tracks Discord game matches with TrueSkill ratings, move histories, and player analytics
- Database is PostgreSQL with ~15 core tables
- Schema version: 1.0.4 with 4 applied migrations

### Problems Identified

Analysis of current schema identified **10 issues** (3 HIGH, 5 MEDIUM, 2 LOW):

- **No audit trail:** Data changes not tracked or attributed
- **Data loss risk:** Cascade deletes remove history permanently
- **Redundant data:** Rating changes stored in multiple places (consistency risk)
- **Lost context:** Replay events have unclear attribution (NULL actor fields)
- **Performance gaps:** View aggregations recomputed on every query
- **Missing constraints:** Business rules not enforced at database level
- **Index gaps:** Missing strategic indices causing table scans
- **No monitoring:** Can't detect constraint violations or data quality issues

---

## Requirements: What Must Be Stored & Retrieved

### 1. Immutable Change Tracking

**Capability Needed:** Every data mutation (INSERT, UPDATE, DELETE) must be captured and stored immutably.

**What Must Be Stored:**

- When the change occurred (timestamp)
- Who triggered the change (user identity or system marker)
- What was changed (table name, record ID, specific columns modified)
- Before and after state (full row snapshots for auditing and potential rollback)
- Why it changed (reason/context code)
- Session/transaction context (for tracing back to source)
- Additional metadata (IP address, API version, etc. if applicable)

**What Must Be Retrievable:**

- Complete change history for any specific record (forward and backward in time)
- All changes made by a specific user during a time period (user activity audit)
- Changes of a specific type (e.g., all DELETEs, all UPDATEs to ratings)
- Transactions that can be rolled back (finding audit records for recovery)
- Change frequency metrics for anomaly detection (e.g., unusual spike in deletions)

**Constraints:**

- Audit log must be immutable (cannot be modified once written)
- Audit log must never be lost due to cascade operations
- Timestamps must be precise enough for ordering events

---

### 2. Consolidated Rating History

**Capability Needed:** Single, authoritative source for all player rating changes (no duplication).

**What Must Be Stored:**

- Which player's rating changed
- Which game the rating applies to
- What type of change occurred (match result, inactivity decay, admin adjustment, system reset)
- The complete before and after rating state (skill estimate + uncertainty)
- Whether change was automatic (system-driven) or explicit (user-driven)
- If explicit: who triggered the change and why
- The event that caused the change (match ID, admin action ID, etc.)
- When the change occurred

**What Must Be Retrievable:**

- A player's complete rating progression over time for a specific game
- All rating changes triggered by a specific match (all participants)
- Player ratings at any point in history (for replay/reconstruction)
- System-generated changes vs. match-driven changes (for reconciliation)
- Rating changes by a specific admin (for accountability)
- Anomalous rating changes (for investigation)

**Constraints:**

- Must not have duplicate records (single source of truth)
- Must support both historical queries and current-state queries
- Must handle edge cases: admin overrides, system resets, skill decay

---

### 3. Event Attribution & Traceability

**Capability Needed:** Replay events must have clear, unambiguous attribution (who/what triggered them).

**What Must Be Stored:**

- What happened in the match (event type: move, forfeit, system reset, etc.)
- When it happened
- Who performed the action (player ID, admin ID, or explicit "system" marker)
- What type of actor it was (player action, admin action, or automatic system action)
- Full event payload (game-specific details)
- Whether the event can be reversed (is it reversible?)
- If reversed: link to the reversal event
- Full audit trail link (connection to immutable audit log)

**What Must Be Retrievable:**

- Complete sequence of events for a match replay (ordered, no gaps)
- All events triggered by a specific player (for user action audit)
- All events of a specific type (moves vs. forfeits vs. system events)
- Reversible vs. irreversible events in a match
- Events that were reversed (for appeal/dispute resolution)
- Events with missing or ambiguous attribution (for investigation)
- Full context for an event (linked audit record)

**Constraints:**

- Attribution must never be NULL without explicit marker (can't lose responsibility)
- Must support appeal/dispute resolution (know what happened and who did it)
- System-driven events must be distinguishable from user actions

---

### 4. Soft-Delete & Data Recovery

**Capability Needed:** Data marked for deletion must remain recoverable; no permanent data loss from cascades.

**What Must Be Stored:**

- Moves/events that have been logically deleted (soft-deleted)
- When deletion occurred
- Who deleted it (user/admin ID)
- Why it was deleted (reason code: match abandoned, dispute resolution, etc.)
- Original data of deleted record (for recovery)
- Archive of hard-deleted records (for long-term recovery/compliance)

**What Must Be Retrievable:**

- Active data only (when querying normally, soft-deleted hidden by default)
- Soft-deleted data (for investigation/recovery)
- Deletion history (who deleted what and when)
- Full archive of permanently deleted records (compliance/recovery)
- Ability to restore deleted records

**Constraints:**

- Soft deletion must be transparent to existing queries (no code changes needed)
- Deleted data must be preserved for minimum 1 year (compliance)
- Soft-deleted records must not break referential integrity

---

### 5. Constraint Enforcement at Database Level

**Capability Needed:** Business rules enforced by database, not just application code.

**Specific Rules:**

- Completed matches must have all participants ranked (no NULL rankings)
- TrueSkill parameters must have valid defaults (consistency)
- Match codes must not have case-sensitivity duplicates
- Replay event actors must be either linked to a user OR explicitly marked as system
- Soft-deleted records must not break related queries
- Rating changes must maintain mu/sigma bounds (no invalid states)

**What Must Be Validated:**

- Data cannot enter invalid states (prevent bad inserts/updates)
- Constraint violations must be detectable (can query what's wrong)
- Business rule violations must fail with clear error messages

**Constraints:**

- Validation must happen at INSERT and UPDATE time
- Errors must be clear enough for debugging
- Should not break backward compatibility

---

### 6. Performance Optimization

**Capability Needed:** Expensive queries must run faster (specifically <200ms for leaderboards).

**Current Performance Issue:**

- Leaderboard queries require expensive GROUP BY aggregations
- Aggregations recomputed on every query
- No pre-computation or caching

**What Must Be Supported:**

- Instant lookup of cached match outcome totals (wins/losses/draws per user/game)
- Fast leaderboard generation from pre-computed rankings
- Quick player stats without full table scans
- Cache freshness tracking (know when cache is stale)
- Cache refresh triggering (update when new match results available)

**What Must Be Retrievable:**

- Cached outcomes (instant lookups)
- Cache staleness (which caches need refresh)
- Performance metrics (hit rates, refresh times)

**Constraints:**

- Cache must not be stale by more than specified threshold (e.g., 1 hour)
- Cache refresh must not block match completion
- Cache must be transparent to most queries

---

### 7. Strategic Indexing

**Capability Needed:** Frequently used query patterns must use efficient indices (not full table scans).

**Query Patterns That Must Be Fast:**

- Leaderboard queries (rank players by game)
- User activity queries (find all matches for a player)
- Replay queries (get all moves in sequence)
- Audit trail queries (find changes by user/table/date range)
- Rating history queries (player progression over time)
- Data quality checks (find constraint violations)

**Constraints:**

- Indices must balance speed vs. storage
- Write performance must not degrade significantly
- Index maintenance must be automatic

---

### 8. Data Quality Monitoring

**Capability Needed:** Continuous validation that data meets business rules; detect violations.

**What Must Be Monitored:**

- Constraint violations (e.g., NULL rankings in completed matches)
- Inconsistencies (e.g., rating history doesn't match current state)
- Anomalies (e.g., unusual rating changes, spike in forfeits)
- Data freshness (e.g., cache staleness)
- Audit trail completeness (e.g., mutations with no audit record)

**What Must Be Retrievable:**

- List of all constraint violations (with severity)
- When violations were first detected
- Which violations are critical vs. warnings
- Violation trend over time (increasing or decreasing)
- Recommended fixes (if auto-fixable)

**Constraints:**

- Monitoring must run continuously (not just on-demand)
- Must not significantly impact performance
- Should alert on critical violations

---

## Acceptance Criteria

### Functional Requirements

✅ **Audit Completeness:** 100% of material data changes captured with actor and reason  
✅ **History Consolidation:** Single source of truth for rating changes (no duplication)  
✅ **Attribution Clarity:** Replay events have unambiguous actor (no ambiguous NULLs)  
✅ **Data Recovery:** Soft-deleted data recoverable for minimum 1 year  
✅ **Constraint Enforcement:** Business rules enforced at database level  
✅ **Performance Target:** Leaderboard queries run in <200ms  
✅ **Index Coverage:** No sequential scans on frequently accessed tables  
✅ **Monitoring:** Data quality violations detected automatically

### Quality Requirements

✅ **Backward Compatibility:** Existing application code works without changes  
✅ **Migration Pattern:** Follows established versioning and deployment procedures  
✅ **Documentation:** Clear how to use audit trail, recovery, monitoring  
✅ **Testing:** Comprehensive tests for all requirements  
✅ **Production Readiness:** Includes rollback procedures and monitoring setup

### Data Retention Requirements

✅ **Audit Log:** Keep 3+ years (compliance and dispute resolution)  
✅ **Rating History:** Indefinite (skill tracking is core to system)  
✅ **Deleted Records Archive:** 1+ year (recovery and compliance)  
✅ **Performance Cache:** 30-minute refresh (doesn't need to persist)  
✅ **Monitoring Data:** 90+ days (trend analysis)

---

## Out of Scope

This requirement does NOT specify:

- Exact SQL schemas or column definitions
- Implementation details (triggers, functions, views)
- Choice of technology (beyond PostgreSQL)
- UI/API changes for accessing audit data
- External audit systems or compliance frameworks

---

## Success Metrics

After implementation is complete, the system should:

| Metric                         | Target | Verification                                         |
|--------------------------------|--------|------------------------------------------------------|
| Audit capture rate             | 100%   | Query audit_log; verify all mutations recorded       |
| Rating history duplication     | 0      | Verify no conflicting records                        |
| Event attribution ambiguity    | 0%     | Query replay_events; verify all have clear actor     |
| Soft-deleted data recovery     | 100%   | Attempt recovery of soft-deleted records             |
| Leaderboard query speed        | <200ms | Performance test under load                          |
| Constraint violation detection | 100%   | Run data quality checks; verify all violations found |
| Backward compatibility         | 100%   | Run existing integration tests; all pass             |
| Data retention compliance      | 100%   | Verify retention policies enforced                   |

---

## Dependencies & Prerequisites

### Must Have (Before Implementation)

- Access to PlayCord PostgreSQL database
- Understanding of current schema and application usage
- Ability to run migrations and deploy updates
- Test environment that mirrors production

### Should Have (For Quality)

- Existing integration test suite
- Performance monitoring/profiling tools
- Staging environment for pre-production validation
- Team familiar with database operations

---

## Implementation Constraints

- **Database:** PostgreSQL (required)
- **Versioning:** Follow semantic versioning (1.0.5 for this work)
- **Migration Pattern:** Must follow PlayCord's existing migration system
- **Testing:** Must pass all existing tests + new test suite
- **Documentation:** Must include audit trail usage guide and recovery procedures
- **Rollback:** Must include rollback/revert procedures

---

## Risk & Mitigation

| Risk                       | Impact   | Mitigation                                                        |
|----------------------------|----------|-------------------------------------------------------------------|
| Performance degradation    | CRITICAL | Comprehensive testing; index strategy; cache design               |
| Data loss during migration | CRITICAL | Backup before migration; staged rollout; dry-run in staging       |
| Backward incompatibility   | HIGH     | Preserve existing APIs; add new capabilities alongside old        |
| Migration lock-up          | HIGH     | Test migration time; add instrumentation; plan maintenance window |
| Audit log explosion        | MEDIUM   | Data retention policy; archive old records; compression           |

---

## Timeline & Phases

### Phase 1: Design Review

- Stakeholder review of requirements
- Technical design decisions (architecture)
- Estimate implementation time

### Phase 2: Implementation

- Build audit trail infrastructure
- Consolidate rating history
- Enforce constraints at DB level
- Optimize performance
- Add data quality monitoring

### Phase 3: Testing & Validation

- Unit tests for all components
- Integration tests with existing code
- Performance testing under load
- Backward compatibility verification

### Phase 4: Documentation & Deployment

- Write audit trail usage guide
- Document recovery procedures
- Write monitoring setup guide
- Deploy to production with rollback plan

---

## Stakeholders & Communication

**Implementer:** Database specialist/agent building the solution  
**Reviewer:** Code reviewer verifying requirements met  
**Deployer:** DevOps/SRE deploying to production  
**Support:** Team handling audit queries, recovery requests  
**Stakeholders:** Project manager, engineering lead

---

## Questions This Requirement Answers

**Q: What data needs to be tracked?**  
A: All material changes (INSERT/UPDATE/DELETE) with who, what, why, when, before/after state

**Q: Why consolidate rating history?**  
A: Eliminate duplication risk; ensure single source of truth for skill progression

**Q: Why soft-delete instead of hard delete?**  
A: Prevent permanent data loss; support recovery and dispute resolution; compliance

**Q: What's the performance target and why?**  
A: <200ms for leaderboards; critical user-facing query must be fast

**Q: How do we know it's working?**  
A: 8 acceptance criteria + success metrics in table above

---

## Next Steps

1. **Review** - Stakeholders review and approve this requirement
2. **Design** - Implementer creates technical design based on these requirements
3. **Implement** - Build solution following requirements (not implementation-specific)
4. **Test** - Verify all acceptance criteria met
5. **Document** - Write usage guide, monitoring setup, recovery procedures
6. **Deploy** - Production deployment with monitoring and rollback plan

---

## Document Control

| Version | Date       | Author         | Status                   |
|---------|------------|----------------|--------------------------|
| 1.0     | 2026-04-25 | Analysis Agent | Ready for Implementation |

**Next Review:** After implementation starts (mid-sprint checkpoint)

---

## Appendix: Issues Being Addressed

This requirement addresses 10 identified schema issues:

1. **HIGH: No immutable audit trail** → Req #1 (Immutable Change Tracking)
2. **HIGH: Missing index on match_participants** → Req #7 (Strategic Indexing)
3. **HIGH: TrueSkill defaults inconsistency** → Req #2 (Rating History)
4. **MEDIUM: Dual history mechanisms** → Req #2 (Rating History)
5. **MEDIUM: View performance (GROUP BY)** → Req #6 (Performance Optimization)
6. **MEDIUM: Case sensitivity in match_code** → Req #5 (Constraint Enforcement)
7. **MEDIUM: No soft-delete (cascade loss)** → Req #4 (Soft-Delete & Recovery)
8. **MEDIUM: Missing analytics index** → Req #7 (Strategic Indexing)
9. **LOW: NULL constraint gap** → Req #5 (Constraint Enforcement)
10. **LOW: Cascade documentation gap** → Req #4 (Soft-Delete & Recovery)

---

**This document is ready to share with implementers, reviewers, and stakeholders.**
