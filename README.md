# Emarat Chatbot

Text-to-SQL and contract-document assistant on the Microsoft Agent Framework
harness, querying Fabric (contracts, sales, contract documents) plus a local
catalog for entity resolution, glossary lookups, and schema search.

---

## Prerequisites

- Python 3.12+
- Node.js 18+ and npm (for the frontend)
- **ODBC Driver 18 for SQL Server** (OS-level install, not pip) —
  [download](https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server)
- Fabric service principal with read-only access to the warehouse
- Azure OpenAI deployment (chat + embeddings)

## Setup

### Backend Setup

```bash
git clone <repo-url>
cd <repo-name>

python -m venv venv
venv\Scripts\activate        # Windows / source venv/bin/activate on macOS/Linux

pip install -r requirements.txt
```

Create `.env`:

```
FABRIC_SERVER=your-workspace.datawarehouse.fabric.microsoft.com
FABRIC_DATABASE=your-warehouse-name
FABRIC_CLIENT_ID=...
FABRIC_CLIENT_SECRET=...
FABRIC_TENANT_ID=...

AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_DEPLOYMENT_NAME=...
AZURE_OPENAI_EMBEDDING_ENDPOINT=https://your-resource.openai.azure.com
AZURE_OPENAI_EMBEDDING_API_KEY=...
AZURE_OPENAI_EMBEDDING_API_VERSION=2024-02-01
AZURE_OPENAI_EMBEDDING_DEPLOYMENT=...

CATALOG_DB_PATH=./catalog.db
```

Never commit `.env`.

### Frontend Setup

```bash
cd frontend
npm install
```

## Build the local catalogs

Catalogs (`catalog.db` and `aviation_catalog.db`) are generated and specific to what's currently in Fabric.

### 1. Build Contracts & Sales Catalog:
```bash
python build/init_catalog_db.py
python build/build_value_catalog.py --with-embeddings
python build/build_schema_catalog.py
python build/build_glossary_catalog.py
python build/build_example_catalog.py
```

### 2. Build Aviation Operations Catalog:
```bash
python build/init_aviation_catalog_db.py
python build/build_aviation_value_catalog.py
python build/build_aviation_schema_catalog.py
python build/build_aviation_glossary_catalog.py
python build/build_aviation_example_catalog.py
```
*(Or run the unified builder: `python build_aviation_catalog.py`)*

## Run

To run the full application (Frontend + FastAPI Backend):

1. **Start the FastAPI Backend:**
   ```bash
   uvicorn api:app --reload --port 8000
   ```
   The API will be available at `http://localhost:8000`.
   *Health check:* `curl http://127.0.0.1:8000/api/health` → `{"status":"ok"}`

2. **Start the React Frontend:**
   Open a new terminal window:
   ```bash
   cd frontend
   npm run dev
   ```
   The UI will be available at `http://localhost:5173`.

**DevUI (quick manual testing, not the production path):**
```bash
python app.py
```
Opens a simple chat UI at `http://localhost:8080`.

---
