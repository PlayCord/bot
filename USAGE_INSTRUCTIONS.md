# How to Use Database Audit Agent Prompt

## Quick Start

Use this prompt with a specialized database or general-purpose agent:

```
Agent: I need you to implement database audit and improvements for PlayCord.

Read and follow the requirements in: DATABASE_AUDIT_AGENT_PROMPT.md

Key success criteria:
- Immutable audit log with full state snapshots
- Consolidated rating history (single source of truth)
- Soft-delete pattern preventing data loss
- Performance optimization via materialized cache
- All new constraints enforced at DB level

Your deliverables should include:
1. SQL migration (version 1.0.5)
2. Trigger functions
3. New views
4. Documentation
5. Tests
```

---

## Prompt Files Overview

### 📄 DATABASE_AUDIT_AGENT_PROMPT.md
**Purpose:** Complete specification for database improvements agent  
**Length:** 12.5 KB  
**Audience:** Database specialist, general-purpose agent  
**Contains:**
- Objective and context
- 8 detailed requirement areas with specific storage/retrieval needs
- All 5 deliverables defined
- Success criteria and agent notes
- Backward compatibility constraints

**Use when:** You want comprehensive, self-contained specification

---

### 📋 DATABASE_AUDIT_QUICK_REFERENCE.md
**Purpose:** Quick lookup guide for implementation  
**Length:** 7.4 KB  
**Audience:** Agent during implementation, code reviewers  
**Contains:**
- Problem statement and 8 requirements at a glance
- SQL schema templates for all new tables
- Trigger definitions
- View definitions
- Index definitions
- Data retention policy
- Sample queries
- Migration pattern

**Use when:** Need quick reference while building, or for peer review

---

### 📊 database_schema_analysis.md
**Purpose:** Analysis of why improvements are needed  
**Length:** 23.5 KB  
**Audience:** Stakeholders, technical decision-makers  
**Contains:**
- Executive summary of 10 issues
- Detailed analysis of each issue
- Root cause, impact, recommendation for each
- Quality checklist
- Priority-based phasing
- Conclusion

**Use when:** Need justification for the work or want to understand issues deeply

---

## Agent Workflow

### Phase 1: Understand Requirements (10 min)
1. Agent reads `DATABASE_AUDIT_AGENT_PROMPT.md` section 1-2 (Objective, Context)
2. Agent reviews "Requirements: What to Store & Retrieve" (Section II)
3. Agent checks "Success Criteria" to understand acceptance conditions

### Phase 2: Design (30 min)
1. Agent creates ERD based on 8 requirement areas
2. Agent uses `DATABASE_AUDIT_QUICK_REFERENCE.md` for schema templates
3. Agent identifies table relationships and indices
4. Agent plans trigger implementations

### Phase 3: Implementation (2-4 hours)
1. Create migration version 1.0.5 following PlayCord pattern
2. Implement audit_log table + 2 indices
3. Implement rating_change_log table + 3 indices
4. Enhance replay_events table + add constraint
5. Add soft-delete columns to match_moves
6. Create match_moves_archive table
7. Create match_outcome_cache table
8. Add all 6+ indices for performance
9. Create all trigger functions (5+ triggers)
10. Create all views (5+ views)

### Phase 4: Testing & Documentation (1-2 hours)
1. Write SQL tests for audit capture
2. Test trigger functionality
3. Verify backward compatibility
4. Write data retention policy
5. Document audit trail usage
6. Create sample recovery queries

### Phase 5: Delivery (30 min)
1. Ensure all files follow PlayCord conventions
2. Provide migration runner instructions
3. Include rollback procedure
4. Provide monitoring setup guide

---

## Example Agent Prompts

### Prompt for General-Purpose Agent

```
Your task: Implement database audit and constraint improvements for PlayCord

Background:
PlayCord is a Discord game bot with TrueSkill rating system. Analysis identified 
10 schema issues (3 HIGH, 5 MEDIUM, 2 LOW) in audit capability, data loss risk, 
and performance.

Requirements:
Read DATABASE_AUDIT_AGENT_PROMPT.md completely. It specifies:
- What data to store (8 requirement areas)
- What queries to support
- How to structure the implementation
- Success criteria and tests needed

Deliverables:
1. SQL migration script (version 1.0.5) - new tables, columns, constraints
2. Trigger functions (5+) - audit, validation, cache invalidation
3. Database views (5+) - reporting and data quality
4. Documentation - ERD, retention policy, usage guide, recovery procedures
5. Tests - verify audit capture, triggers, backward compatibility

Use DATABASE_AUDIT_QUICK_REFERENCE.md as your implementation checklist.

Your solution must:
✅ Be backward compatible (existing code continues to work)
✅ Follow PlayCord's migration pattern (semantic versioning in db_migrations.py)
✅ Include comprehensive comments
✅ Provide sample queries for common use cases
✅ Pass all success criteria tests
```

### Prompt for Database Specialist Agent

```
Implement audit trail and performance optimization for PlayCord PostgreSQL schema.

The full specification is in DATABASE_AUDIT_AGENT_PROMPT.md.

Key objectives:
1. Create immutable audit log capturing all data mutations
2. Consolidate dual rating history mechanisms
3. Add soft-delete pattern to prevent data loss
4. Materialize expensive view aggregations
5. Enforce business constraints at DB level

Constraints:
- Must preserve backward compatibility
- Use PostgreSQL features optimally (JSONB, composite indices, IMMUTABLE)
- Follow existing migration versioning (1.0.5)
- Comprehensive documentation required

Acceptance: Must meet all 8 success criteria + pass test suite.
```

---

## Integration with Code Review

### For Code Reviewer

1. Check against `DATABASE_AUDIT_QUICK_REFERENCE.md` schema templates
2. Verify all 8 requirement areas implemented
3. Confirm success criteria met
4. Check backward compatibility
5. Review documentation completeness

### Review Checklist

- [ ] All new tables created with specified columns
- [ ] All indices created and tested
- [ ] All triggers implemented and tested
- [ ] All views created
- [ ] Audit log captures 100% of material changes
- [ ] Rating history consolidated (no duplication)
- [ ] Soft-delete pattern prevents data loss
- [ ] Materialized cache improves performance
- [ ] Constraints enforced at DB level
- [ ] Migration follows PlayCord pattern
- [ ] Backward compatibility verified
- [ ] Documentation complete
- [ ] Sample queries provided
- [ ] Data retention policy defined

---

## Common Questions

**Q: Should I modify existing tables or only add new ones?**  
A: Both. The prompt specifies enhancements to `replay_events`, `match_moves`, and 
`match_participants`. All changes must be backward compatible.

**Q: Do I need to migrate existing data?**  
A: Create migration that handles existing data:
- Populate `audit_log` with placeholder entries for historical changes
- Denormalize existing `rating_history` into `rating_change_log`
- Populate `match_outcome_cache` for all user/game combinations

**Q: What's the performance target?**  
A: Leaderboard queries should run in <200ms (currently slow due to repeated GROUP BY).
The materialized cache should achieve this.

**Q: Do I create a new migration file or add to schema.sql?**  
A: Follow PlayCord pattern: Add to `MIGRATIONS` list in `playcord/utils/db_migrations.py`
as versioned entry (1.0.5), with SQL statements in tuple. This allows clean rollback.

**Q: Should I preserve the old views?**  
A: Yes, keep `v_match_outcomes` but modify it to use the new cache. All existing views
that depend on it should continue to work transparently.

---

## Success Indicators

After agent implements the requirements, you should see:

✅ Migration 1.0.5 registered and runnable  
✅ New audit_log table populated (even with placeholder historical data)  
✅ Rating history consolidated into new rating_change_log  
✅ Soft-deleted moves tracked but not lost  
✅ Match outcome cache pre-computed (staleness tracked)  
✅ All constraints enforced via triggers  
✅ Data quality checks table with initial checks  
✅ All new views accessible and tested  
✅ Documentation including ERD and usage guide  
✅ Tests passing (audit capture, trigger validation, cache performance)  
✅ Existing queries continue to work without code changes  

---

## Next Steps After Implementation

1. **Deploy:** Run migration in staging; verify all checks pass
2. **Monitor:** Watch cache hit rates, audit log growth, trigger performance
3. **Validate:** Run data quality checks; verify no constraint violations
4. **Document:** Update runbook with new monitoring procedures
5. **Train:** Brief team on new audit and recovery capabilities

---

## File Locations

```
PlayCord/pythonProject/
├── DATABASE_AUDIT_AGENT_PROMPT.md          (Full specification)
├── DATABASE_AUDIT_QUICK_REFERENCE.md       (Quick lookup)
├── AGENT_PROMPT_SUMMARY.md                 (This overview)
└── USAGE_INSTRUCTIONS.md                   (This file)

Session folder (analysis):
└── database_schema_analysis.md             (Issue analysis)
```

---

## Support for Agent

If agent encounters ambiguities:

1. Check `DATABASE_AUDIT_AGENT_PROMPT.md` section "Agent Notes"
2. Refer to PlayCord codebase: `playcord/infrastructure/db/sql/`
3. Review existing migration pattern in `playcord/utils/db_migrations.py`
4. Check existing views in `views.sql` for similar patterns

The prompt is designed to be self-contained; if agent has questions not answered 
by the prompt, clarify requirements before proceeding.
