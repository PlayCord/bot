# Requirements-Only Prompt Summary

## What This Is

A **pure requirements specification** that defines WHAT needs to be built, not HOW to build it.

**Perfect for:**
- Stakeholder approval
- Architectural decision-making
- Agents designing their own solutions
- Requirements documentation
- RFP/vendor evaluation

---

## File: DATABASE_AUDIT_REQUIREMENTS.md

### What's Inside (No Implementation Details)

✅ **8 Capability Areas** (what must be stored/retrieved)  
✅ **Acceptance Criteria** (8 functional + 3 quality checkpoints)  
✅ **Success Metrics** (measurable verification)  
✅ **Data Retention Policy** (compliance requirements)  
✅ **Risk Mitigation** (known issues + solutions)  
✅ **Constraints** (database choice, versioning, testing)  

### What's NOT Included

❌ SQL schemas or table definitions  
❌ Trigger implementations  
❌ View specifications  
❌ Index configurations  
❌ Migration SQL code  
❌ Any implementation prescriptions  

---

## The 8 Requirements Explained (High-Level)

### 1. Immutable Change Tracking
**Need:** Capture all data mutations (who, what, when, why, before/after)  
**Goal:** Enable full audit trails, compliance, and rollback capability

### 2. Consolidated Rating History
**Need:** Single source of truth for player rating changes (no duplication)  
**Goal:** Reliable skill progression tracking; eliminate consistency risks

### 3. Event Attribution & Traceability
**Need:** Clear accountability for all replay events (never ambiguous NULL)  
**Goal:** Support dispute resolution; know who/what triggered every action

### 4. Soft-Delete & Data Recovery
**Need:** Recoverable deletions; no permanent data loss from cascades  
**Goal:** Compliance, appeals, investigation; 1+ year retention

### 5. Constraint Enforcement
**Need:** Business rules enforced at database level, not just application  
**Goal:** Prevent invalid data states; catch errors early

### 6. Performance Optimization
**Need:** Fast queries for leaderboards and player stats (<200ms)  
**Goal:** Better user experience; scalability

### 7. Strategic Indexing
**Need:** Efficient indices for all common query patterns  
**Goal:** No table scans; consistent performance

### 8. Data Quality Monitoring
**Need:** Continuous detection of constraint violations and anomalies  
**Goal:** Early warning of data problems; self-healing capability

---

## How to Use This Prompt

### For Stakeholders/Approvers
1. Read the **Executive Summary**
2. Review **8 Capability Areas**
3. Check **Acceptance Criteria** (is this what you want?)
4. Approve or iterate

### For Architects/Designers
1. Read full document
2. Review **Constraints** (database choice, versioning)
3. Review **Dependencies & Prerequisites**
4. Design technical approach to meet requirements

### For Implementers
1. Read full document to understand goals
2. Design solution that meets all acceptance criteria
3. Verify against success metrics
4. Choose HOW to implement (agent has freedom)

### For Reviewers
1. Use **Acceptance Criteria** as verification checklist
2. Use **Success Metrics** to validate implementation
3. Verify against **Data Retention** requirements
4. Check **Backward Compatibility** requirement

---

## Key Differences from Implementation Prompt

| Aspect | Implementation Prompt | Requirements Prompt |
|--------|----------------------|---------------------|
| **Level** | Detailed (HOW) | Strategic (WHAT) |
| **SQL** | Specific schemas | No schemas |
| **Triggers** | Defined | Defined at high level only |
| **Views** | Listed | Mentioned as examples |
| **Flexibility** | Prescriptive | Implementer chooses solution |
| **Use Case** | Developer | Stakeholder / Architect |
| **Length** | 12.5 KB | 16.9 KB |

---

## Acceptance Criteria (What Success Looks Like)

### Functional
- ✅ Audit captures 100% of changes
- ✅ No duplicate rating records
- ✅ Event attribution unambiguous
- ✅ Soft-deleted data recoverable
- ✅ Business rules enforced at DB
- ✅ Leaderboards <200ms
- ✅ No sequential scans
- ✅ Quality violations detected

### Quality
- ✅ Existing code works unchanged
- ✅ Follows PlayCord patterns
- ✅ Fully documented
- ✅ Comprehensive tests

### Compliance
- ✅ 3+ year audit retention
- ✅ 1+ year deleted data retention
- ✅ Rollback procedures included

---

## Success Metrics (Verification Table)

| Metric | Target | How to Verify |
|--------|--------|---------------|
| Audit capture | 100% | Query audit log |
| Duplication | 0% | Check for conflicts |
| Attribution | 0% ambiguous | Check for NULL issues |
| Recovery | 100% | Restore deleted record |
| Query speed | <200ms | Performance test |
| Violations | 100% found | Run data quality checks |
| Compatibility | 100% | Run existing tests |
| Retention | 100% | Verify policies enforced |

---

## When to Use Which Prompt

### Use DATABASE_AUDIT_REQUIREMENTS.md When:
- Need stakeholder approval
- Creating RFP/vendor request
- Making architectural decisions
- Team designing the solution
- Want flexibility in implementation
- Doing requirements documentation

### Use DATABASE_AUDIT_AGENT_PROMPT.md When:
- Ready to delegate to agent
- Need specific implementation
- Want least ambiguity
- Team prefers prescribed solution
- Fast execution is priority

---

## Benefits of This Approach

✅ **Flexibility** - Implementer can choose best approach  
✅ **Clarity** - Stakeholders understand what they're getting  
✅ **Decoupling** - Requirements independent of technology choices  
✅ **Testing** - Easy to verify against requirements  
✅ **Maintenance** - Requirements don't change if implementation changes  

---

## Risks If Skipped

❌ Implementers guess at intent  
❌ Stakeholders expect different outcome  
❌ Over/under-engineering possible  
❌ Hard to verify completion  
❌ Disputes over what was needed  

---

## Next Steps

### 1. Approve Requirements
- [ ] Stakeholders review DATABASE_AUDIT_REQUIREMENTS.md
- [ ] Get feedback on acceptance criteria
- [ ] Adjust if needed
- [ ] Sign off

### 2. Create Technical Design
- [ ] Architect reviews requirements
- [ ] Creates technical design document
- [ ] Chooses implementation approach (SQL migration, triggers, views, etc.)
- [ ] Estimates effort

### 3. Implement
- [ ] Team builds solution
- [ ] Verifies against acceptance criteria
- [ ] Tests against success metrics

### 4. Review & Deploy
- [ ] Code review using acceptance criteria
- [ ] Validation testing
- [ ] Production deployment

---

## How This Fits with Other Prompts

```
1. database_schema_analysis.md
   ↓ (identifies issues)
   
2. DATABASE_AUDIT_REQUIREMENTS.md  ← This document
   ↓ (what needs to be built)
   
3. DATABASE_AUDIT_AGENT_PROMPT.md
   ↓ (specific how-to instructions)
   
4. Implementation by Agent
   ↓ (actual code/SQL)
   
5. Validation against requirements
   ↓ (acceptance testing)
   
6. Deployment
```

---

## Document Features

### Clear Organization
- Executive summary
- 8 numbered requirements
- Acceptance criteria
- Success metrics
- Appendix linking to issues

### Measurable Goals
- Performance targets (<200ms)
- Retention periods (3 years, 1 year, etc.)
- Completion percentage (100%)
- Data quality metrics

### Low Ambiguity
- Each requirement has subsections: "What must be stored" + "What must be retrieved"
- Examples of queries/operations
- Clear constraints

### Stakeholder Friendly
- No technical jargon
- Business terms used
- Risk section addresses concerns
- Timeline provided

---

## Validation Checklist

Before sharing this requirement, verify:

- [ ] 8 requirements clearly stated
- [ ] Each requirement has "What to store" and "What to retrieve" sections
- [ ] Acceptance criteria are objective (not subjective)
- [ ] Success metrics are measurable
- [ ] Constraints are realistic
- [ ] Data retention policy is defined
- [ ] No implementation details leak in
- [ ] Backward compatibility explicitly mentioned

---

## Questions This Answers

**Q: What do we need to build?**  
A: 8 capability areas (audit, history, attribution, soft-delete, constraints, performance, indices, monitoring)

**Q: How do we know when it's done?**  
A: 8 acceptance criteria + success metrics table

**Q: What if we need to change something later?**  
A: Requirements are independent of implementation; adjust and re-implement

**Q: Can we use this for RFP?**  
A: Yes, it's technology-neutral and outcome-focused

**Q: What about performance targets?**  
A: <200ms for leaderboards; derived from user experience goals

---

## Summary

This requirements document:

✅ Defines WHAT without prescribing HOW  
✅ Is measurable (success metrics)  
✅ Is verifiable (acceptance criteria)  
✅ Is stakeholder-friendly (no jargon)  
✅ Enables flexibility (implementer chooses approach)  
✅ Prevents disputes (clear acceptance)  

**Perfect for architectural decisions and requirements documentation.**

---

**File:** DATABASE_AUDIT_REQUIREMENTS.md (16.9 KB)  
**Use When:** Need requirements-only, no implementation details  
**Share With:** Stakeholders, architects, reviewers
