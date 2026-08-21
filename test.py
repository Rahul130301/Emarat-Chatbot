from tools.validation import validate_sql
result = validate_sql.func(  # or however your @tool wrapper exposes the underlying function
    "SELECT c.company_name, SUM(c.contract_value) AS total_contract_value, "
    "COUNT(s.sale_id) AS sales_count FROM contracts AS c LEFT JOIN sales AS s "
    "ON c.company_name = s.company_name GROUP BY c.company_name "
    "ORDER BY total_contract_value DESC, c.company_name ASC;"
)
print(result)