# Cleaning Rule Configuration

After the user confirms deterministic rules, represent them in a JSON configuration accepted by `scripts/apply_cleaning.py --rules rules_config.json`. Semantic judgments do not belong in this file; keep them in the separately audited judgment layer.

## Top-level shape

```json
{
  "meta": {
    "dataset": "dataset-name-or-id",
    "cleaning_mode": "standard",
    "auto_apply": false,
    "confirmed_at": "2026-09-03",
    "metadata_available": {
      "userid": true,
      "ip": true,
      "ua": true,
      "submit_time": true,
      "duration": false
    }
  },
  "id_field": "serial",
  "rules": []
}
```

- `metadata_available` records which signals were observed during profiling. A rule whose required signal is unavailable must be reported as constrained rather than silently run with substitutes.
- `id_field` is the stable, respondent-visible identifier used in audit output. For WeJot exports, use `serial`.
- `cleaning_mode` is `conservative`, `standard`, or `aggressive`.
- If `auto_apply` is false, even a `hard_remove` disposition is marked for approval rather than physically removed.

## Rule object

| Field | Required | Meaning |
|---|---|---|
| `rule_id` | yes | Stable library or project rule identifier |
| `name` | yes | Human-readable rule name |
| `enabled` | yes | Whether to evaluate the rule |
| `disposition` | yes | `hard_remove` or `flag` |
| `target` | rule-specific | Field or question identifiers |
| `params` | rule-specific | Thresholds, valid values, or logical conditions |

Example:

```json
{
  "rule_id": "S1",
  "name": "Speeder",
  "enabled": true,
  "disposition": "flag",
  "params": {
    "total_duration_factor": 0.4,
    "median_per_item_sec": 8,
    "item_count": 25
  }
}
```

Range, straight-line, skip-logic, contradiction, outlier, and duplicate rules should encode only fields and operations supported by the deterministic script. Do not place arbitrary executable code in `params`.

## Output contract

The cleaning script produces:

1. a cleaned data copy; rows marked for removal remain present when `auto_apply` is false;
2. an audit log containing stable identifier, rule, target, evidence, disposition, and whether the action was applied;
3. a summary containing hits by rule, removal and review counts, and constrained rules.

Merge semantic-review decisions with this audit only after the user confirms final disposition.

## Expression safety

When a contradiction rule supports expressions, available names are dataset columns plus explicitly derived values such as survey year. Permit only documented boolean and comparison operators, null checks, and safe numeric functions. If a rule cannot be represented safely, route it to semantic review instead of executing arbitrary code.
