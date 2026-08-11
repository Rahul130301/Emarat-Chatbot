---
name: bar-chart
description: >
  Use this skill when the user asks for a bar chart, bar graph, column chart,
  or wants to visually compare a measure across distinct categories such as
  industries, companies, contract statuses, renewal types, sales regions, or
  time periods (months/quarters).
---

## When to activate this skill

Use bar chart when:
- The user says "bar chart", "bar graph", "column chart", "compare", "ranking"
- The question compares a measure (contract value, revenue, contract count)
  across categories
- Categories are discrete (industry, company, status, renewal_type,
  sales_region, contract_owner, month)

Examples that fit: "compare contract value by industry", "rank companies by
revenue", "show contract count by status", "sales by region last quarter"

Do NOT use for proportional breakdowns (parts of a whole) — use the
pie-chart skill for those instead.

## Output Format

After running SQL and getting real result rows, output ONLY a `json:chart`
fenced code block. No text inside the block — raw JSON only.

### Schema

```json
{
  "type": "bar",
  "title": "A clear descriptive title",
  "description": "One-line subtitle: what measure, what scope, what filter",
  "x_label": "What the categories represent (e.g. Industry, Company, Month)",
  "y_label": "What the values represent (e.g. Total Contract Value ($), Revenue ($))",
  "data": [
    { "name": "Category Label", "value": 12345.67 }
  ]
}
```

### Field definitions

- `"name"` → the category label exactly as it appears in the data (e.g. an
  `industry` value like "Healthcare", a `company_name`, a `status`). Never
  invent or reformat a category that isn't actually in the result rows.
- `"value"` → the raw number from the SQL result for that category — a sum,
  count, or average, whatever the question asked for. Never a percentage,
  never pre-scaled.

### Rules

- Only include categories that actually appear in the query result — never
  pad with a zero-value category that wasn't returned.
- If the result has more than ~15 categories, keep only the top N by value
  (state in `description` that it's a top-N view) rather than cramming every
  category into one unreadable chart.
- Sort `data` descending by `value` unless the categories have a natural
  order (e.g. months chronologically) — in that case use that order instead.