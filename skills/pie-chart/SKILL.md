---
name: pie-chart
description: >
  Use this skill when the user asks for a pie chart, donut chart, breakdown,
  share, distribution, or proportion of contracts or sales — for example:
  "what share of contract value comes from healthcare?" or "breakdown of
  contracts by status".
---

## When to activate this skill

Use pie chart when:
- The user says "pie chart", "breakdown", "share", "proportion",
  "percentage of", "distribution"
- The question asks how a total is split across groups (e.g. contract value
  by industry, contract count by status, revenue by region)
- The parts logically add up to a meaningful whole (100%)

Examples that fit: "breakdown of contracts by status", "what share of
revenue comes from each region?", "distribution of contract value by
renewal type"

Do NOT use for comparisons where values don't form a meaningful whole (e.g.
"compare contract value across industries" without caring about the total) —
use bar-chart instead.

## Output Format

After running SQL and getting real result rows, output ONLY a `json:chart`
fenced code block. No other text inside the block — raw JSON only.

### Schema

```json
{
  "type": "pie",
  "title": "A clear descriptive title",
  "description": "One-line subtitle explaining what is being broken down",
  "unit": "$",
  "data": [
    { "name": "Slice Label", "value": 46776.25, "percentage": 22.7 }
  ]
}
```

## Field Definitions — READ CAREFULLY

- `"value"` → THE RAW NUMBER DIRECTLY FROM THE SQL RESULT. This is the
  actual contract value, revenue amount, or count — whatever the query
  returned. It is NEVER a percentage. NEVER divide, NEVER multiply by 100.
  Copy it exactly as-is from the query result.
- `"percentage"` → A SEPARATE field you compute yourself AFTER you have all
  the raw values. Formula: `round((this_item_value / sum_of_all_values) * 100, 1)`.
  This is NOT the same as `value`. Both fields must be present on every slice.
- `"unit"` → the actual unit of the values, matching the domain you're in.
  Use `"$"` for money, `"L"` for litres/fuel volume, `"%"` for a percentage
  measure, `""` for a plain count. NEVER default to `"$"` for a non-money
  metric — e.g. aviation fuel volume must use `"unit": "L"`, not `"$"`.

### Rules

- Only include categories that actually appear in the query result.
- Percentages across all slices should sum to approximately 100 (rounding
  may cause a small drift — that's fine, don't force-adjust it).
- If there are more than ~8 slices, group the smaller ones into an "Other"
  slice (sum their values, sum their percentages) rather than producing an
  unreadable pie with a dozen slivers.