# tools/ontology_check.py
"""Ontology-based semantic validation for generated SQL. Checks the query
against the actual relationship cardinalities in the knowledge graph:
- undefined join (no relationship in the graph at all) -> warning
- aggregate on the "one"/parent side of a one-to-many join, without
  collapsing the many side first -> block (classic fan-out double-count)
- many-to-many join (neither side unique) with any aggregate -> block
"""
import sqlglot
from sqlglot import exp
from db import get_current_database
from graph_db import get_driver


def _clean(name: str) -> str:
    return name.strip("[]").split(".")[-1]


def _get_relationship_map(database: str) -> dict:
    """table -> {other_table: 'many_to_one' | 'one_to_many' | 'many_to_many'}
    from THIS table's perspective looking at the other table."""
    with get_driver().session() as session:
        rows = session.run(
            """
            MATCH (many:Table {database:$db})-[r:REFERENCES]->(one:Table {database:$db})
            RETURN many.name AS many_t, one.name AS one_t, r.cardinality AS cardinality
            """,
            db=database,
        )
        rel_map = {}
        for row in rows:
            many_t, one_t, card = row["many_t"], row["one_t"], row["cardinality"]
            if card == "many_to_one":
                rel_map.setdefault(many_t, {})[one_t] = "many_to_one"
                rel_map.setdefault(one_t, {})[many_t] = "one_to_many"
            else:
                rel_map.setdefault(many_t, {})[one_t] = "many_to_many"
                rel_map.setdefault(one_t, {})[many_t] = "many_to_many"
    return rel_map


def _table_alias_map(parsed) -> dict:
    mapping = {}
    for t in parsed.find_all(exp.Table):
        mapping[_clean(t.alias_or_name)] = _clean(t.name)
    return mapping


def _extract(sql: str):
    parsed = sqlglot.parse_one(sql, read="tsql")
    alias_map = _table_alias_map(parsed)

    from_tables = set()
    from_clause = parsed.find(exp.From)
    if from_clause:
        for t in from_clause.find_all(exp.Table):
            from_tables.add(_clean(t.name))

    joins = []
    seen = set(from_tables)
    for join in parsed.find_all(exp.Join):
        join_table = join.this
        if isinstance(join_table, exp.Table):
            right = _clean(join_table.name)
            for left in seen:
                joins.append((left, right))
            seen.add(right)

    agg_tables, agg_distinct = [], []
    for agg in parsed.find_all(exp.AggFunc):
        col = agg.find(exp.Column)
        table = alias_map.get(_clean(col.table)) if (col is not None and col.table) else None
        agg_tables.append(table)
        agg_distinct.append(bool(agg.args.get("distinct")))

    query_distinct = parsed.args.get("distinct") is not None
    return joins, agg_tables, agg_distinct, query_distinct


def check_ontology(sql: str) -> list[str]:
    try:
        joins, agg_tables, agg_distinct, query_distinct = _extract(sql)
    except Exception as e:
        return [f"WARNING: could not parse query for ontology check ({e}) — skipped."]

    if not joins or not agg_tables:
        return []

    rel_map = _get_relationship_map(get_current_database())
    issues = []

    for left, right in joins:
        cardinality = rel_map.get(left, {}).get(right)
        if cardinality is None:
            issues.append(
                f"WARNING: join between '{left}' and '{right}' has no defined "
                f"relationship in the schema graph — verify this join is correct."
            )
            continue

        one_side = right if cardinality == "many_to_one" else left if cardinality == "one_to_many" else None

        if one_side:
            for table, distinct in zip(agg_tables, agg_distinct):
                if table == one_side and not distinct and not query_distinct:
                    other = left if one_side == right else right
                    issues.append(
                        f"BLOCK: aggregating a column from '{one_side}' after joining to "
                        f"'{other}' can double-count — '{one_side}' is the single/parent "
                        f"side here, and each of its rows may match multiple '{other}' rows. "
                        f"Pre-aggregate '{other}' first (e.g. GROUP BY the join key in a "
                        f"subquery), or aggregate a column from '{other}' instead."
                    )
        else:  # many_to_many
            if any(not d for d in agg_distinct) and not query_distinct:
                issues.append(
                    f"BLOCK: '{left}' and '{right}' join on a key that isn't unique on "
                    f"either side — any aggregate here can double-count rows on both "
                    f"sides. Aggregate each table separately before joining."
                )
    return issues