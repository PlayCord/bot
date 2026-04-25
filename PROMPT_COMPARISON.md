# Database Audit Prompts - Comparison Guide

## Three Levels of Specification

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         REQUIREMENTS LEVEL                                  │
│              (WHAT needs to be built - no implementation)                    │
│                                                                              │
│  DATABASE_AUDIT_REQUIREMENTS.md                                             │
│  • 8 capability areas (high-level)                                          │
│  • What to store & retrieve (functional)                                    │
│  • Acceptance criteria (objective)                                          │
│  • Success metrics (measurable)                                             │
│  • Constraints (not how-tos)                                                │
│                                                                              │
│  Audience: Stakeholders, architects, requirements folks                     │
│  Use: Approval, design, RFP, flexibility                                    │
└─────────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│                       SPECIFICATION LEVEL                                    │
│              (HOW to build it - detailed prescription)                       │
│                                                                              │
│  DATABASE_AUDIT_AGENT_PROMPT.md                                             │
│  • 8 requirement areas (detailed)                                           │
│  • Specific schemas (exact columns)                                         │
│  • Table designs (with constraints)                                         │
│  • Trigger specifications                                                   │
│  • View definitions                                                         │
│  • Index designs                                                            │
│                                                                              │
│  Audience: Developers, agents, builders                                     │
│  Use: Implementation, direct execution, no ambiguity                        │
└─────────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│                         ANALYSIS LEVEL                                       │
│              (WHY improvements needed - problem deep-dive)                    │
│                                                                              │
│  database_schema_analysis.md                                                │
│  • 10 specific issues identified                                            │
│  • Root cause analysis for each                                             │
│  • Business impact assessment                                               │
│  • Prioritized recommendations                                              │
│  • Quality checklist                                                        │
│                                                                              │
│  Audience: Decision-makers, stakeholders, architects                        │
│  Use: Justification, business case, issue understanding                     │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Comparison Matrix

| Dimension | Requirements Prompt | Implementation Prompt | Analysis |
|-----------|-------------------|--------------------|----|
| **File** | DATABASE_AUDIT_REQUIREMENTS.md | DATABASE_AUDIT_AGENT_PROMPT.md | database_schema_analysis.md |
| **Size** | 16.9 KB | 12.5 KB | 23.5 KB |
| **Focus** | WHAT (outcomes) | HOW (approach) | WHY (problems) |
| **Detail Level** | High-level | Detailed | Deep analysis |
| **Contains SQL** | No | Yes (schemas) | No |
| **Contains Triggers** | Mentioned only | Fully defined | No |
| **Contains Views** | General concept | Specific designs | No |
| **Contains Indices** | Listed | Specific designs | No |
| **Prescriptive** | No | Very | No |
| **Flexible** | Yes | No | N/A |
| **Primary Use** | Approval, design | Development | Justification |
| **Secondary Use** | RFP, vendor requests | Architecture | Business case |

---

## When to Use Each

### DATABASE_AUDIT_REQUIREMENTS.md
```
Use When:
✓ Need stakeholder buy-in
✓ Creating RFP/vendor request
✓ Multiple implementation approaches possible
✓ Architectural decision-making
✓ Requirements documentation needed
✓ Team designing their own solution

Typical Users:
- Project manager
- Stakeholder/sponsor
- Architect
- Requirements analyst
```

### DATABASE_AUDIT_AGENT_PROMPT.md
```
Use When:
✓ Ready to delegate to agent/developer
✓ Want specific, prescriptive solution
✓ Need minimal ambiguity
✓ Want fast execution
✓ Team prefers "just tell me what to build"

Typical Users:
- Developer
- Agent/AI assistant
- Implementer
- "Just execute" teams
```

### database_schema_analysis.md
```
Use When:
✓ Need to justify the work
✓ Explaining why changes needed
✓ Decision-making on priorities
✓ Risk assessment
✓ Impact analysis

Typical Users:
- Engineering lead
- Stakeholder
- Decision-maker
- Problem investigator
```

---

## Workflow Examples

### Scenario 1: Stakeholder Approval Process
```
1. Read: database_schema_analysis.md (2026-04-24)
   ↓ Understand the 10 issues

2. Present: DATABASE_AUDIT_REQUIREMENTS.md
   ↓ Get stakeholder buy-in on what's needed

3. Approve: Requirements signed off
   ↓ Proceed to implementation phase
```

### Scenario 2: Design-Driven Implementation
```
1. Review: DATABASE_AUDIT_REQUIREMENTS.md
   ↓ Understand WHAT (outcomes)

2. Design: Architecture team creates design doc
   ↓ Architect chooses HOW (approach)

3. Implement: Developer/agent builds
   ↓ Follow design, meet requirements
```

### Scenario 3: Direct Delegation
```
1. Hand over: DATABASE_AUDIT_AGENT_PROMPT.md
   ↓ All details specified

2. Build: Agent implements exactly as specified
   ↓ No ambiguity, fast execution

3. Verify: Code review against spec
   ↓ Done
```

### Scenario 4: RFP/Vendor Request
```
1. Use: DATABASE_AUDIT_REQUIREMENTS.md
   ↓ Vendor-neutral, outcome-focused

2. Send to vendors: "Please propose solution meeting these requirements"
   ↓ Vendors submit different technical approaches

3. Evaluate: Which vendor's approach is best?
   ↓ Award contract
```

---

## Content Comparison Detail

### Requirements Prompt (DATABASE_AUDIT_REQUIREMENTS.md)
```
✓ 8 Capability Areas
  • What must be stored (business terms)
  • What must be retrieved (query patterns)
  • Constraints (functional, not technical)

✓ Acceptance Criteria (8 + 3 + retention)
  • All objective/measurable
  • No "nice to have"

✓ Success Metrics
  • Performance targets
  • Retention periods
  • Coverage percentages

✗ NO SQL schemas
✗ NO trigger code
✗ NO view definitions
✗ NO index specifications
✗ NO implementation details
```

### Implementation Prompt (DATABASE_AUDIT_AGENT_PROMPT.md)
```
✓ 8 Requirement Areas
  • Full column specs (types, constraints)
  • Complete table schemas
  • JSONB structure specifications

✓ Trigger Functions
  • Function names
  • Purpose
  • When they fire

✓ Views
  • Column definitions
  • Join logic
  • Filter conditions

✓ Indices
  • Specific index designs
  • WHERE clauses for partial indices
  • Column order

✓ Migration Pattern
  • Version number
  • SQL syntax
  • Idempotent operations

✓ Sample Queries
  • Specific SQL examples
✗ NO flexibility (prescriptive)
✗ NO architectural decisions left open
```

---

## Key Differences Illustrated

### Requirement #1: Immutable Change Tracking

**Requirements Version:**
```
What Must Be Stored:
- When the change occurred
- Who triggered it
- What was changed
- Before and after state
- Why it changed

What Must Be Retrievable:
- Complete history for any record
- All changes by a user in time period
- Changes of specific type
- Transactions that can be rolled back
```

**Implementation Version:**
```
Table: audit_log
Columns:
- audit_id BIGSERIAL PK
- timestamp TIMESTAMPTZ
- actor_user_id BIGINT (nullable)
- operation_type VARCHAR (INSERT/UPDATE/DELETE/SYSTEM_EVENT)
- table_name VARCHAR
- record_id BIGINT
- before_state JSONB
- after_state JSONB
- ...

Indices:
- (table_name, record_id, timestamp DESC)
- (actor_user_id, timestamp DESC) WHERE actor_user_id IS NOT NULL
```

**Notice:** Requirements don't dictate schema; implementation does.

---

## Flexibility Comparison

### Requirements Prompt: Implementation Options
```
Requirement: "Immutable audit log with full state snapshots"

Possible implementations:
1. Single audit_log table (simple)
2. Partitioned audit_log by date (performance)
3. Separate table per domain (modularity)
4. Event sourcing pattern (architectural)
5. Time-series database (scalability)

All valid - requirements don't care HOW
```

### Implementation Prompt: No Options
```
Requirement: Specific schema for audit_log table

Only one way to do it - exactly as specified

Good for: Fast execution, no ambiguity
Bad for: Flexibility, innovation, learning
```

---

## Choosing the Right Prompt

```
DECISION TREE:

Is there ambiguity about what needs to be built?
├─ YES
│  ├─ Do you need stakeholder approval?
│  │  └─ YES → Use: DATABASE_AUDIT_REQUIREMENTS.md
│  │  └─ NO → Use: database_schema_analysis.md
│
├─ NO
│  ├─ Are you ready to delegate to an agent/developer?
│  │  └─ YES → Use: DATABASE_AUDIT_AGENT_PROMPT.md
│  │  └─ NO → Use: DATABASE_AUDIT_REQUIREMENTS.md (design phase)
```

---

## Document Stack

For maximum effectiveness, use all three:

```
1. database_schema_analysis.md
   └─ "Here's why we need to do this"
   
2. DATABASE_AUDIT_REQUIREMENTS.md
   └─ "Here's what success looks like"
   
3. DATABASE_AUDIT_AGENT_PROMPT.md
   └─ "Here's exactly how to build it"
```

Progression from understanding → approval → execution

---

## Quick Reference

| Need | Document | Why |
|------|----------|-----|
| Understand problems | analysis | Issues explained |
| Get approval | requirements | Outcomes clear |
| Make design decisions | requirements | Flexible approach |
| Delegate to developer | implementation | No ambiguity |
| Evaluate vendors | requirements | Neutral, outcome-focused |
| Write RFP | requirements | Clear scope |
| Build quickly | implementation | Prescriptive |
| Teach team | requirements | Conceptual |
| Execute precisely | implementation | Detailed |

---

## Summary

**Three documents, three purposes:**

1. **Requirements** - WHAT (outcomes, acceptance, success)
2. **Implementation** - HOW (schemas, code, specifics)
3. **Analysis** - WHY (problems, justification, issues)

**Choose based on your need:**
- Approval? → Requirements
- Delegation? → Implementation
- Justification? → Analysis
- All three? → Maximum effectiveness
