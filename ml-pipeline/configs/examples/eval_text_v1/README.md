# EVAL-TEXT-V1 examples (not benchmark data)

| File | Use |
| --- | --- |
| `SCHEMA-ILLUSTRATION-ONLY.query.jsonl` | Shows exact eight query fields; **do not import** |
| `SCHEMA-ILLUSTRATION-ONLY.judgment.jsonl` | Shows six judgment fields; UUID is placeholder only |
| `query_coverage_tracker.template.csv` | Copy locally; plan 40 queries before JSONL export |
| `coordinator_query_assignments.template.csv` | Pre-assigned IDs, splits, classes, intent groups, authors (14/13/13) |
| `judgment_progress_tracker.template.csv` | Copy locally; track 32k primary rows + adjudication |

Authoritative workflow: [docs/TEXT-QUERY-V1-WORKFLOW.md](../../../docs/TEXT-QUERY-V1-WORKFLOW.md)  
Coordinator checklist: [docs/EVAL-TEXT-V1-COORDINATOR-CHECKLIST.md](../../../docs/EVAL-TEXT-V1-COORDINATOR-CHECKLIST.md)
