# ContextIQ — Codebase Guide (kahan kya ho raha hai)

> Ye file ek **guided tour** hai: har file me kya code hai, konsa function kya karta hai, aur newcomer ke liye **kis order me** padhna chahiye. Jodi diagram-level samajh chahiye to [ARCHITECTURE.md](ARCHITECTURE.md) dekho.

---

## 🧭 Padhne ka order (newcomer ke liye)

Naya aadmi codebase samajhne ke liye is order me file padhe:

```
1. main.py                      ← app yahan se start hoti hai
2. app/application.py           ← FastAPI assemble hoti hai
3. app/core/config.py           ← saari settings (.env) yahan
4. app/api/routes.py            ← 3 endpoints
5. app/models/schemas.py        ← request/response ka shape
6. app/services/rag_service.py  ← sab kuch yahan wire hota hai (DIL)
7. app/rag/ingestion.py         ← PDF → vectors (write path)
8. app/rag/pipeline.py          ← question → answer (read path)
9. services/*_service.py        ← ChromaDB, LLM, embeddings ke wrappers
10. app/utils/*                 ← helpers (cleaning, errors)
```

> **Sabse important file:** [app/services/rag_service.py](app/services/rag_service.py) — yahi "composition root" hai jahan har cheez jud-ti hai. Confuse ho jao to wapas yahan aao.

---

## 📂 File-by-file breakdown

### `main.py` — Entry point
> [main.py](main.py)

- App yahan se chalti hai: `python main.py` ya `uvicorn main:app --reload`.
- `app = create_app()` — application factory ko call karke ASGI app banata hai.
- `uvicorn.run(...)` — server `0.0.0.0:8000` pe, `reload=True` ke saath start karta hai.

**Yaad rakho:** ye file sirf "start button" hai. Asli logic kahin aur hai.

---

### `app/application.py` — FastAPI factory
> [app/application.py](app/application.py)

Yahan FastAPI app banti aur configure hoti hai:

| Cheez | Line | Kaam |
|---|---|---|
| `lifespan()` | [L27-39](app/application.py#L27-L39) | Startup pe `get_rag_service()` call karke heavy resources (embeddings, vector store) pehle se warm-up kar leta hai → pehli request fast. |
| `create_app()` | [L43-72](app/application.py#L43-L72) | App banata hai, title/version set karta hai. |
| CORS middleware | [L56-61](app/application.py#L56-L61) | `allow_origins=["*"]` — frontend (`:3000`) backend se baat kar sake. |
| `_rag_error_handler` | [L64-69](app/application.py#L64-L69) | Koi bhi `RAGError` ko proper HTTP response (status + `{detail}`) me badal deta hai. |

---

### `app/core/config.py` — Saari settings
> [app/core/config.py](app/core/config.py)

Ye **single source of truth** hai. `.env` se sab kuch yahan load hota hai (`pydantic-settings`).

- `LLMProvider`, `EmbeddingProvider` — [L18-32](app/core/config.py#L18-L32) — supported providers ke enums (openai / gemini / ollama / huggingface).
- `Settings` class — [L35-104](app/core/config.py#L35-L104) — har env variable ek typed field. Provider, API keys, model names, chunk size, top_k, temperature, paths — sab yahan.
- `_overlap_must_be_smaller_than_size` — [L83-89](app/core/config.py#L83-L89) — validation: overlap < chunk_size hona chahiye.
- `ensure_directories()` — [L101-104](app/core/config.py#L101-L104) — `data/` folders bana deta hai.
- `get_settings()` — [L107-110](app/core/config.py#L107-L110) — `@lru_cache` ke saath singleton (poore process me ek hi Settings object).

**Kuch badalna ho (model, chunk size, provider)?** Code nahi — `.env` badlo. Naya field add karna ho to yahan add karo.

---

### `app/api/routes.py` — Teen endpoints
> [app/api/routes.py](app/api/routes.py)

Yahan HTTP layer hai. Teeno endpoints `RAGService` ko `Depends(get_rag_service)` se inject karke use karte hain.

| Endpoint | Function | Line | Kya karta hai |
|---|---|---|---|
| `GET /health` | `health()` | [L38-48](app/api/routes.py#L38-L48) | Status + providers + kitne chunks indexed. |
| `POST /upload-pdf` | `upload_pdf()` | [L51-93](app/api/routes.py#L51-L93) | PDF validate (`.pdf`, content-type, ≤25MB, non-empty) → disk pe save → `service.ingest_pdf()` call. |
| `POST /ask` | `ask()` | [L96-103](app/api/routes.py#L96-L103) | `service.ask(question, top_k)` call karke answer return. |

**Important pattern:** CPU/IO-bound kaam (`ingest_pdf`, `ask`) ko `run_in_threadpool(...)` me bhejte hain — taaki async event loop block na ho. Isiliye endpoints genuinely async rehte hain.

---

### `app/models/schemas.py` — API ka contract
> [app/models/schemas.py](app/models/schemas.py)

Pydantic models jo request/response ka shape define karte hain (aur auto-validation + OpenAPI docs dete hain):

- `HealthResponse` — [L15-23](app/models/schemas.py#L15-L23)
- `UploadResponse` — [L29-37](app/models/schemas.py#L29-L37) — `filename`, `chunks_created`, `pages`.
- `AskRequest` — [L43-57](app/models/schemas.py#L43-L57) — `question` (required) + optional `top_k`.
- `AskResponse` — [L60-67](app/models/schemas.py#L60-L67) — **sirf `answer`** (confidence/sources jaanbujhke expose nahi kiye).
- `ErrorResponse` — [L73-76](app/models/schemas.py#L73-L76) — `{detail}` envelope.

---

### `app/services/rag_service.py` — Composition root (DIL ❤️)
> [app/services/rag_service.py](app/services/rag_service.py)

Yahi woh jagah hai jahan sab kuch jud-ta hai. Har dusra module isi se mil ke kaam karta hai.

- `RAGService.__init__` — [L30-44](app/services/rag_service.py#L30-L44):
  - `build_embeddings()` → embeddings client banata hai.
  - `VectorStoreService(...)` → ChromaDB taiyaar.
  - `IngestionPipeline(...)` → write path taiyaar.
  - **LLM yahan NAHI banta** — woh lazy hai (niche dekho).
- `document_count()` — [L53-55](app/services/rag_service.py#L53-L55) — kitne chunks indexed hain.
- `ingest_pdf()` — [L60-62](app/services/rag_service.py#L60-L62) — ingestion pipeline ko delegate.
- `ask()` — [L64-71](app/services/rag_service.py#L64-L71) — **pehli baar** call hone par LLM + RAG pipeline banata hai (lazy), fir answer deta hai.
- `get_rag_service()` — [L80-85](app/services/rag_service.py#L80-L85) — process-wide singleton (FastAPI DI isi ko use karta hai).

**Lazy LLM kyun?** Taaki bina LLM key ke bhi PDF upload/ingest ho sake. LLM sirf `/ask` pe chahiye.

---

### `app/rag/ingestion.py` — Write path (PDF → vectors)
> [app/rag/ingestion.py](app/rag/ingestion.py)

PDF ko clean, chunked, metadata-rich documents me badalta hai.

- `IngestionResult` — [L30-36](app/rag/ingestion.py#L30-L36) — output: filename, pages, chunks_created.
- `__init__` — [L42-54](app/rag/ingestion.py#L42-L54) — `RecursiveCharacterTextSplitter` setup (size=1000, overlap=150, natural separators).
- `ingest()` — [L59-90](app/rag/ingestion.py#L59-L90) — **main orchestrator**: load → clean → chunk → store.
- `_load()` — [L95-107](app/rag/ingestion.py#L95-L107) — PyPDFLoader se per-page documents. Fail → `InvalidPDFError`.
- `_clean()` — [L109-124](app/rag/ingestion.py#L109-L124) — text saaf, khaali pages drop. Sab khaali → `EmptyPDFError` (scanned PDF ho sakti hai).
- `_chunk()` — [L126-140](app/rag/ingestion.py#L126-L140) — chunks banata hai + har ek pe `source/page/chunk_index` metadata.

Embedding + storage khud nahi karta — `VectorStoreService.add_documents()` ko deta hai.

---

### `app/rag/pipeline.py` — Read path (question → answer)
> [app/rag/pipeline.py](app/rag/pipeline.py)

Asli RAG chain yahan hai. **Yahi file aap IDE me khole hue ho.**

- `_SYSTEM_PROMPT` — [L34-47](app/rag/pipeline.py#L34-L47) — **grounding rules** (sirf context se jawab, bahar ki knowledge nahi, na mile to "Content not found in the PDF.").
- `RetrievedChunk` / `RAGAnswer` — [L52-66](app/rag/pipeline.py#L52-L66) — data structures.
- `RAGPipeline.__init__` — [L72-85](app/rag/pipeline.py#L72-L85) — LangChain chain banata hai: `prompt | llm | StrOutputParser` (LCEL).
- `answer()` — [L87-145](app/rag/pipeline.py#L87-L145) — **main method**:
  1. Empty index check → `NoDocumentsError`.
  2. `similarity_search` → top-K chunks.
  3. `_format_context` → context block.
  4. Chain invoke → LLM answer.
  5. "Not found" handle + confidence.
- `_format_context()` — [L150-161](app/rag/pipeline.py#L150-L161) — chunks ko source-labelled text block me jodta hai.
- `_confidence()` — [L163-174](app/rag/pipeline.py#L163-L174) — `0.5·best + 0.5·mean(top-3)` similarity.

---

### `app/services/vectorstore_service.py` — ChromaDB wrapper
> [app/services/vectorstore_service.py](app/services/vectorstore_service.py)

Sirf yahi file ChromaDB ko directly jaanti hai (storage swappable rehta hai).

- `__init__` — [L24-44](app/services/vectorstore_service.py#L24-L44) — persistent Chroma collection (disk pe, restart-safe).
- `add_documents()` — [L49-65](app/services/vectorstore_service.py#L49-L65) — chunks embed + store (ingestion use karta hai).
- `similarity_search()` — [L70-96](app/services/vectorstore_service.py#L70-L96) — query embed → top-K chunks. **Distance ko similarity (0-1) me convert** karta hai: `1/(1+distance)`.
- `count()` — [L98-103](app/services/vectorstore_service.py#L98-L103) — kitne vectors stored.

---

### `app/services/llm_service.py` — LLM factory
> [app/services/llm_service.py](app/services/llm_service.py)

- `build_llm(settings)` — [L18-76](app/services/llm_service.py#L18-L76) — `settings.llm_provider` dekh ke sahi chat model banata hai:
  - `openai` → `ChatOpenAI` (key chahiye)
  - `gemini` ✅ → `ChatGoogleGenerativeAI` (abhi yahi active)
  - `ollama` → `ChatOllama` (local, no key)
- Provider packages **lazily import** hote hain (jo use ho wahi install chahiye).

---

### `app/services/embedding_service.py` — Embeddings factory
> [app/services/embedding_service.py](app/services/embedding_service.py)

- `build_embeddings(settings)` — [L19-85](app/services/embedding_service.py#L19-L85) — `settings.embedding_provider` dekh ke embeddings client:
  - `openai` → `OpenAIEmbeddings`
  - `gemini` ✅ → `GoogleGenerativeAIEmbeddings` (abhi active)
  - `huggingface` → `HuggingFaceEmbeddings` (local, normalize on)
  - `ollama` → `OllamaEmbeddings` (local)

`llm_service.py` jaisa hi pattern — provider switch = `.env` change.

---

### `app/utils/` — Helpers

- [app/utils/text_cleaning.py](app/utils/text_cleaning.py) — `clean_text()`: PDF se nikla raw text normalise/saaf karta hai (ingestion me use hota hai).
- [app/utils/exceptions.py](app/utils/exceptions.py) — domain errors, har ek ke saath `status_code`:

| Exception | Status | Kab |
|---|---|---|
| `InvalidPDFError` | 400 | File valid PDF nahi |
| `EmptyPDFError` | 422 | PDF me extractable text nahi |
| `NoDocumentsError` | 409 | Bina upload kiye sawaal pucha |
| `MissingAPIKeyError` | 500 | Provider ki key missing |
| `VectorStoreError` | 500 | ChromaDB fail |
| `LLMError` | 502 | LLM generate nahi kar paaya |

Ye sab `RAGError` se inherit karti hain, aur [application.py](app/application.py) ka handler inhe HTTP response me badal deta hai.

---

### `app/core/logging_config.py` — Logging
> [app/core/logging_config.py](app/core/logging_config.py)

- `configure_logging(level)` — app startup pe logging setup.
- `get_logger(name)` — har module isse logger leta hai (`logger.info(...)`).

---

## 🔁 "Agar mujhe X badalna ho to kahan jaun?" — Quick map

| Kaam | Jagah |
|---|---|
| Model / provider switch | [.env](.env) (`LLM_PROVIDER`, `EMBEDDING_PROVIDER`, `LLM_MODEL`...) |
| Chunk size / overlap | [.env](.env) → use hota hai [ingestion.py](app/rag/ingestion.py#L49-L54) me |
| Kitne chunks retrieve | [.env](.env) `RETRIEVAL_TOP_K` → [pipeline.py](app/rag/pipeline.py#L101) |
| Answer ka tone / grounding rules | `_SYSTEM_PROMPT` [pipeline.py:34](app/rag/pipeline.py#L34-L47) |
| Naya provider add karna | [llm_service.py](app/services/llm_service.py) / [embedding_service.py](app/services/embedding_service.py) |
| Naya endpoint | [routes.py](app/api/routes.py) + [schemas.py](app/models/schemas.py) |
| Naya config field | [config.py](app/core/config.py) `Settings` |
| Storage backend badalna | sirf [vectorstore_service.py](app/services/vectorstore_service.py) |
| API response me confidence/sources expose karna | [schemas.py](app/models/schemas.py) `AskResponse` + [routes.py](app/api/routes.py#L96-L103) |
| Upload size limit | [routes.py:35](app/api/routes.py#L35) `_MAX_PDF_BYTES` |

---

## 🧪 Tests
> [tests/](tests/)

- [tests/test_api.py](tests/test_api.py) — endpoints ke tests.
- [tests/test_text_cleaning.py](tests/test_text_cleaning.py) — text cleaning logic.

Chalane ke liye: `pytest` (venv activate karke).
```
