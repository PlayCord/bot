# Database Audit Agent Prompt - Summary

## Files Created

1. **DATABASE_AUDIT_AGENT_PROMPT.md** (12.5 KB)
   - Complete comprehensive prompt for another agent
   - Covers all requirements in detail
   - Includes context, deliverables, success criteria

2. **DATABASE_AUDIT_QUICK_REFERENCE.md** (7.4 KB)
   - Quick lookup guide with tables, triggers, views
   - SQL schemas for new tables
   - Indices and constraint reference

## What the Agent Prompt Contains

### 📋 Objective
Implement comprehensive audit trail, constraint enforcement, and performance optimization for PlayCord database to address 10 identified schema issues.

### 🔍 Context Provided
- Reference to all 10 issues found (3 HIGH, 5 MEDIUM, 2 LOW)
- Current problematic patterns
- Business impact of each issue

### 📦 Requirements (8 Core Areas)

1. **Immutable Audit Log** - Track all data changes with full state snapshots
2. **Unified Rating History** - Consolidate redundant history mechanisms
3. **Replay Event Attribution** - Add actor_type to clarify NULL cases
4. **Soft-Delete & Archive** - Prevent data loss with soft-delete pattern
5. **Match Completion Validation** - Enforce NOT NULL constraints via triggers
6. **Performance Optimization** - Materialized cache for expensive views
7. **Index Optimization** - Add 6+ strategic compound indices
8. **Data Quality Monitoring** - Continuous validation checks

### 📊 Specific Details for Each Requirement

For each requirement, the prompt specifies:
- **What to store** - All columns, types, constraints
- **What to retrieve** - Query patterns and access methods
- **Performance considerations** - Indices, refresh strategies
- **Examples** - Sample SQL and use cases

### ✅ Deliverables Defined

1. SQL migration script (versioned, idempotent)
2. Trigger functions (5+ new triggers)
3. Database views (5+ new views)
4. Documentation (ERD, retention policy, usage guide)
5. Tests (mutation capture, performance, data quality)

### 🎯 Success Criteria

8 explicit criteria covering:
- 100% audit capture with actor/reason
- Zero data loss via soft-delete + archive
- Single rating history source of truth
- Clear replay event attribution
- <200ms leaderboard queries
- Constraint violation detection
- Rollback/recovery capability
- Backward compatibility

### ⚠️ Agent Notes

- Preserve backward compatibility
- Use PostgreSQL features (JSONB, composite indices)
- Follow existing migration pattern (semantic versioning)
- Comprehensive documentation
- Sample queries for common use cases

---

## How to Use These Prompts with Another Agent

### Option 1: Direct Prompt
Pass the full `DATABASE_AUDIT_AGENT_PROMPT.md` to a specialized database agent:

```
"I need you to design and implement database improvements. Here are the requirements:
[paste full prompt]"
```

### Option 2: Staged Approach
Use the quick reference first for planning, then the full prompt for implementation:

1. Agent reads `DATABASE_AUDIT_QUICK_REFERENCE.md` for high-level overview
2. Agent reads `DATABASE_AUDIT_AGENT_PROMPT.md` for detailed requirements
3. Agent creates SQL migration + triggers + views + tests

### Option 3: Supplemental Context
Combine with the analysis report for full context:

- **DATABASE_SCHEMA_ANALYSIS.md** - Why each issue matters
- **DATABASE_AUDIT_AGENT_PROMPT.md** - What to build
- **DATABASE_AUDIT_QUICK_REFERENCE.md** - How to build it

---

## Key Differentiators in This Prompt

✅ **Comprehensive** - 8 distinct requirement areas with specific storage/retrieval needs  
✅ **Actionable** - SQL schemas, indices, and constraints defined  
✅ **Tested** - Success criteria and test coverage specified  
✅ **Production-Ready** - Migration pattern, documentation, retention policy included  
✅ **Backward Compatible** - Explicitly preserves existing functionality  
✅ **Self-Contained** - Agent doesn't need to refer back to analysis or ask clarifying questions  

---

## Next Steps

### For Database Agent:
1. Read `DATABASE_AUDIT_AGENT_PROMPT.md` completely
2. Use `DATABASE_AUDIT_QUICK_REFERENCE.md` as implementation checklist
3. Create SQL migration following PlayCord's pattern (version 1.0.5)
4. Implement triggers in `functions.sql`
5. Add views in `views.sql`
6. Write comprehensive documentation
7. Create tests to verify all requirements met

### For Project Manager:
- Share both prompt files with database specialist
- Review SUCCESS CRITERIA section for acceptance
- Plan for backward compatibility testing
- Schedule review after migration deployment

---

## Files Location

- `DATABASE_AUDIT_AGENT_PROMPT.md` - Full detailed prompt
- `DATABASE_AUDIT_QUICK_REFERENCE.md` - Quick reference checklist
- `database_schema_analysis.md` - Analysis of current issues (in session folder)

All files are ready for sharing with another agent or team member.
