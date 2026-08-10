# ContextIQ - Advanced RAG & Multi-Doc Chat System

ContextIQ is an enterprise-grade, production-ready **Retrieval-Augmented Generation (RAG)** system. Upload files (.pdf, .docx, .txt, .csv), switch focus between documents in real-time, and chat with their content through a modern Obsidian Nebula dashboard.

---

## ✨ Advanced Features

* **Multi-Format Ingestion** — Dynamic support for loading and parsing PDF, DOCX, TXT, and CSV formats.
* **Single Document Focus** — Selectively query a single file from your history. Queries are strictly filtered in ChromaDB using metadata tags (`source`).
* **Conversational Memory** — Multi-turn chat support with contextual query condensation (LLM-based question rewriting).
* **Hybrid Search (Vector + BM25)** — Merges semantic vector similarities and lexical keyword ranks using Reciprocal Rank Fusion (RRF).
* **Cross-Encoder Re-ranking** — Lazy loads a local deep-learning cross-encoder model (`ms-marco-MiniLM-L-6-v2`) to re-score and re-sort retrieved chunks.
* **Web Search Fallback** — Automatically routes queries to DuckDuckGo search if matching document context is missing or similarity is low.
* **Document Management** — Instantly list indexed documents and delete them (clearing vectors from ChromaDB and unlinking physical storage from disk).
* **PostgreSQL & JWT Authentication** — Secure multi-user setup using JWT tokens, custom username registration, password hashing, and user-level multi-tenant document isolation in ChromaDB.
* **Obsidian Nebula Dashboard** — A 100% responsive, glassy frontend layout supporting drag-and-drop uploads, scroll timelines, mobile drawer menus, and grounding citations overlays.

---

## 🏗️ Architecture

```
                         ┌──────────────────────────────────────────┐
                         │               Next.js UI                 │
                         │    (Obsidian Nebula Dashboard Layout)    │
                         └───────────────────┬──────────────────────┘
                                             │
                         ┌──────────────────────────────────────────┐
                         │               FastAPI API                │
                         │  /auth (S/L)   /upload   /ask   /documents│
                         └───────┬───────────────┬──────────────────┘
                                 │               │
                  ┌──────────────▼──┐        ┌───▼───────────────┐
   INGEST (write) │ IngestionPipeline│  ASK  │   RAGPipeline      │ (read)
                  └──────────────┬──┘        └───┬───────────────┘
   PDF Loader / Word Loader /    │               │  Condense Question
   CSV & TXT Loader              │               │  Hybrid Search (Vector + BM25)
   Clean Text & Chunker          │               │  Cross-Encoder Rerank
   Embed                         │               │  DuckDuckGo Fallback (optional)
        │                        │               │  Ground generation
        ▼                        ▼               ▼        │
   ┌───────────┐         ┌────────────────────────┐  ┌────▼────┐
   │ Embeddings│◄────────┤      ChromaDB           │  │   LLM   │
   │ OpenAI /  │         │  (persistent on disk)   │  │ OpenAI /│
   │ Gemini /  │         └────────────────────────┘  │ Gemini  │
   │ HuggingFace│                                    └─────────┘
   └───────────┘
```

---

## 📁 Project Structure

```
ContextIQ/
├── app/
│   ├── api/              # API endpoints (Upload, Ask, Documents list/delete)
│   │   └── routes.py
│   ├── application.py    # Startup lifespan, CORS, and exception routers
│   ├── core/             # Configuration & logging setups
│   │   ├── config.py
│   │   ├── database.py   # PostgreSQL/SQLite engine and session pooler
│   │   └── logging_config.py
│   ├── models/           # Request/response models
│   │   └── schemas.py
│   ├── rag/              # Ingestion & generation pipelines
│   │   ├── ingestion.py  # Loader routing & clean text chunker
│   │   └── pipeline.py   # Condensation, Reranking, and Web Fallback
│   ├── services/         # Service composition layers
│   │   ├── embedding_service.py
│   │   ├── llm_service.py
│   │   ├── vectorstore_service.py
│   │   └── rag_service.py
│   └── utils/            # Domain exceptions and auth utilities
│       ├── exceptions.py
│       ├── text_cleaning.py
│       └── auth.py       # Password hash and JWT token codecs
├── frontend/             # Next.js (TypeScript / Tailwind) Dashboard UI
│   ├── src/app/
│   │   ├── page.tsx      # Main layout component
│   │   └── globals.css   # Dark Obsidian styles & mobile drawer media
│   └── src/lib/api.ts    # Frontend API client
├── data/
│   ├── pdfs/             # Local upload storage
│   └── chroma_db/        # Persistent vector store database
├── tests/                # Pytest suites
├── requirements.txt      # Python dependencies
├── main.py               # Backend entry point
└── README.md
```

---

## 🚀 Setup & Installation

### 1. Backend Setup (FastAPI)

Requires **Python 3.13+**.

```bash
# Activate virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment variables
cp .env.example .env

# Run FastAPI
uvicorn main:app --reload
```
Interactive API docs are available at **http://localhost:8000/docs**.

### 2. Frontend Setup (Next.js)

Requires **Node.js 18+**.

```bash
cd frontend

# Install package dependencies
npm install

# Start the dev server
npm run dev
```
Open **http://localhost:3000** in your browser to load the dashboard.

---

## 📡 API Usage

### `POST /auth/signup`
Registers a new user with email, password, and custom username.
```bash
curl -X POST http://localhost:8000/auth/signup \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "mypassword", "username": "Prafull"}'
```

### `POST /auth/login`
Verifies user credentials and returns a signed JWT access token and custom username.
```bash
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "mypassword"}'
```

### `GET /health`
Returns system heartbeat, active embedding/LLM providers, and indexed counts.
```bash
curl http://localhost:8000/health
```

### `POST /upload`
Ingests a PDF, DOCX, TXT, or CSV file.
```bash
curl -X POST http://localhost:8000/upload \
  -F "file=@/path/to/resume.docx"
```

### `GET /documents`
Lists unique filenames currently indexed in the system.
```bash
curl http://localhost:8000/documents
```

### `DELETE /documents/{filename}`
Deletes a document from the vector store and unlinks it from disk storage.
```bash
curl -X DELETE http://localhost:8000/documents/resume.docx
```

### `POST /ask`
Queries the grounded RAG pipeline. Accepts conversational history and a focused document source name.
```bash
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{
    "question": "What is my name?",
    "selected_document": "resume.docx",
    "history": [
      {"role": "user", "content": "Hello!"},
      {"role": "assistant", "content": "Hi, how can I help you today?"}
    ]
  }'
```

---

## 🧪 Running Tests

To run the automated backend test suite, run:
```bash
venv/bin/pytest -v
```

---

## 🔁 Switching Providers (no code changes)

Configure cloud APIs or run fully local setups by updating `.env`:

**Google Gemini Setup (Cloud):**
```env
LLM_PROVIDER=gemini
EMBEDDING_PROVIDER=gemini
GOOGLE_API_KEY=AIzaSy...
LLM_MODEL=gemini-flash-latest
EMBEDDING_MODEL=models/gemini-embedding-001
```

**Ollama Setup (Fully Local):**
```env
LLM_PROVIDER=ollama
EMBEDDING_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
LLM_MODEL=llama3.1
EMBEDDING_MODEL=nomic-embed-text
```
