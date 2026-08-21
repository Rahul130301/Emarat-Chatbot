# Emarat Chatbot

Text-to-SQL and contract-document assistant built on the Microsoft Agent Framework. It answers natural-language questions against Microsoft Fabric warehouses (contracts/sales + aviation uplifts) using a grounded tool pipeline: local SQLite catalogs for entity/schema/glossary resolution, then validated read-only SQL against Fabric.

---

## Architecture

```
Frontend (React / Vite :5173)
        │  POST /chat or /chat/fast  (SSE)
        ▼
FastAPI (api.py :8000)
        │  selects agent + switches Fabric DB + catalog path
        ▼
Agent (agent.py | aviation_agent.py)
        │  Azure OpenAI tool-calling loop
        ▼
Tools ──► Local SQLite catalogs (entity / schema / glossary / examples)
      └──► Fabric warehouse via pyodbc (schema introspection, validate, run)
```

**Two domains**

| Domain | Agent module | Fabric warehouse | Local catalog |
|--------|--------------|------------------|---------------|
| Contracts & sales | `agent.py` | `FABRIC_DATABASE` (default `contract-warehouse`) | `catalog.db` |
| Aviation uplifts | `aviation_agent.py` | `FABRIC_AVIATION_DATABASE` (default `aviation-warehouse`) | `aviation_catalog.db` |

Per request, `api.py` sets the active Fabric database and catalog path via context vars (`set_current_database` / `set_current_catalog_path`) so the same tool implementations serve both domains.

**Two latency modes**

| Mode | Endpoint | Behavior |
|------|----------|----------|
| Reasoning | `POST /chat` | Harness agent: narrated `<reasoning>` tags, todo list, full tool set including `search_example_sql` |
| Fast | `POST /chat/fast` | Plain tool-calling agent: silent pipeline, parallel independent tool calls, skips `search_example_sql` (and `list_tables` for contracts) |

Accuracy guarantees (entity resolution, schema lookup, `validate_sql` before `run_sql`) are shared; Fast only drops narration and style-aid tools.

---

## SQL generation flow

The agent does not emit SQL from a single prompt. It follows a fixed multi-step tool pipeline encoded in the agent instructions (`DOMAIN_INTRO` / `AVIATION_DOMAIN_INTRO`). Skipping or reordering steps is explicitly forbidden.

### Contracts agent (structured questions)

```
User question
    │
    ▼
1. Intent classification (silent)
   STRUCTURED | DOCUMENT | HYBRID
    │
    ├─ STRUCTURED ──────────────────────────────────────────────┐
    │                                                           │
    ▼                                                           │
2. Entity extraction                                            │
   (company, industry, status, product, region, …)              │
    │                                                           │
    ▼                                                           │
3. resolve_entity  →  value_catalog (+ aliases / fuzzy / embed / LLM)
    │                                                           │
    ▼                                                           │
4. lookup_glossary_term  →  glossary_catalog (business → table/column)
    │                                                           │
    ▼                                                           │
5. search_schema_graph  →  knowledge_graph (semantic join-aware schema)
    │                                                           │
    ▼                                                           │
6. get_table_schema  →  Fabric sys.columns (exact column names/types)
    │                                                           │
    ▼                                                           │
7. lookup_metric  →  glossary_catalog metrics (pre-approved SQL patterns)
    │                                                           │
    ▼                                                           │
8. search_example_sql  →  example_sql_catalog  [Reasoning only]
    │                                                           │
    ▼                                                           │
9. SQL generation (model writes SELECT using only resolved names)│
    │                                                           │
    ▼                                                           │
10. validate_sql  →  Fabric SELECT TOP 0 * FROM (query) AS …     │
    │     INVALID → fix → re-validate                           │
    ▼                                                           │
11. run_sql  →  Fabric (read-only SELECT, max 50 rows returned)  │
    │                                                           │
    ▼                                                           │
12. Plain-language answer (+ optional json:chart via skills)    │
                                                            ◄───┘
```

**DOCUMENT mode** resolves company → `contract_id` via validated SQL, then calls `get_contract_document` and answers from clause text only.

**HYBRID mode** runs the structured filter first, then opens matching contract documents and synthesizes both results.

### Aviation agent

Same pattern, scoped to `[dbo].[aviation-uplifts]`: resolve airline/aircraft/stand/flight entities → glossary/metric → schema → (examples in Reasoning) → `validate_sql` → `run_sql` → answer with volumes in Litres (`unit: "L"` for charts).

### Fast-mode batching

Independent discovery tools are issued in the same turn:

1. Parallel: `resolve_entity` (all entities) + `lookup_glossary_term` + `search_schema_graph`
2. Parallel: `get_table_schema` for every relevant table
3. Sequential only: `validate_sql` → (must be VALID) → `run_sql`

Optional: set `AZURE_OPENAI_FAST_DEPLOYMENT_NAME` to a smaller/faster deployment for Fast mode.

---

## Tool reference

| Tool | Source of truth | Role |
|------|-----------------|------|
| `resolve_entity` | `value_catalog` + `tools/aliases.json` | Map user phrases → canonical DB values (exact → alias → fuzzy ≥0.6 → embedding ≥0.90 → LLM) |
| `lookup_glossary_term` | `glossary_catalog` (`entry_type=term`) | Business language → table/column |
| `lookup_metric` | `glossary_catalog` (`entry_type=metric`) | Named metric → approved SQL pattern |
| `search_schema_graph` | `knowledge_graph` | Join-aware schema search with relationship context |
| `search_example_sql` | `example_sql_catalog` | Similar Q→SQL patterns (top 3); Reasoning only |
| `list_tables` | Fabric `sys.tables` | Enumerate tables (aviation Fast keeps it; contracts Fast drops it) |
| `get_table_schema` | Fabric `sys.columns` | Exact column names and types |
| `validate_sql` | Fabric compile via `SELECT TOP 0 * FROM (…)` | Read-only check + object existence; sanitizes aviation table names |
| `run_sql` | Fabric query execution | SELECT only; returns `ROWS RETURNED: N` + rows |
| `get_contract_document` | Fabric `contract_documents` | Full markdown for a `contract_id` (contracts agent only) |

Skills under `./skills` (bar-chart, pie-chart) are loaded via `SkillsProvider` and define the `json:chart` fenced-block schema when the user asks for a chart.

---

## API

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/login` | Returns `session_id` (30 min idle timeout) |
| `POST` | `/logout` | Clears session (`Authorization: Bearer <session_id>`) |
| `POST` | `/chat` | Reasoning stream (SSE); body: `{ message, session_id, agent_type }` |
| `POST` | `/chat/fast` | Fast stream (SSE); same body |

`agent_type`: `"contracts"` (default) or `"aviation"`.

SSE events include `text`, optional `tool_call` / `todos` (Reasoning), and end with `data: [DONE]`.

On startup, `api.py` warms Fabric connection pools in a background thread so the first `validate_sql` / `run_sql` avoids a cold AAD handshake (~2.5–3s).

---

## Prerequisites

- Python 3.12+
- Node.js 18+ and npm (frontend)
- **ODBC Driver 18 for SQL Server** (OS install, not pip) —
  [download](https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server)
- Fabric service principal with read-only warehouse access
- Azure OpenAI deployment (chat + embeddings)

## Setup

### Backend

```bash
git clone <repo-url>
cd <repo-name>

python -m venv venv
venv\Scripts\activate        # Windows / source venv/bin/activate on macOS/Linux

pip install -r requirements.txt
```

Create `.env` (never commit it):

```
FABRIC_SERVER=your-workspace.datawarehouse.fabric.microsoft.com
FABRIC_DATABASE=contract-warehouse
FABRIC_AVIATION_DATABASE=aviation-warehouse
FABRIC_CLIENT_ID=...
FABRIC_CLIENT_SECRET=...
FABRIC_TENANT_ID=...

AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_DEPLOYMENT_NAME=...
AZURE_OPENAI_FAST_DEPLOYMENT_NAME=...   # optional; Fast mode model

AZURE_OPENAI_EMBEDDING_ENDPOINT=https://your-resource.openai.azure.com
AZURE_OPENAI_EMBEDDING_API_KEY=...
AZURE_OPENAI_EMBEDDING_API_VERSION=2024-02-01
AZURE_OPENAI_EMBEDDING_DEPLOYMENT=...

CATALOG_DB_PATH=./catalog.db
AVIATION_CATALOG_DB_PATH=./aviation_catalog.db
```

### Frontend

```bash
cd frontend
npm install
```

## Build the local catalogs

Catalogs are generated from what is currently in Fabric.

### Contracts & sales

```bash
python build/init_catalog_db.py
python build/build_value_catalog.py --with-embeddings
python build/build_schema_catalog.py
python build/build_glossary_catalog.py
python build/build_example_catalog.py
```

### Aviation operations

```bash
python build/init_aviation_catalog_db.py
python build/build_aviation_value_catalog.py
python build/build_aviation_schema_catalog.py
python build/build_aviation_glossary_catalog.py
python build/build_aviation_example_catalog.py
```

Or the unified builder: `python build_aviation_catalog.py`

## Run

1. **API**

   ```bash
   uvicorn api:app --reload --port 8000
   ```

   API: `http://localhost:8000`

2. **Frontend** (separate terminal)

   ```bash
   cd frontend
   npm run dev
   ```

   UI: `http://localhost:5173`

**DevUI** (quick manual testing, not the production path):

```bash
python app.py
```

Opens a simple chat UI at `http://localhost:8080`.
