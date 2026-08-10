"""API tests using a fake RAGService.

These tests exercise the HTTP layer (routing, validation, response shapes,
error mapping) WITHOUT loading real embedding models or calling an LLM, by
overriding the ``get_rag_service`` dependency with a lightweight fake.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from langchain_core.documents import Document

from app.application import create_app
from app.core.config import get_settings
from app.rag.ingestion import IngestionResult
from app.rag.pipeline import RAGAnswer, RetrievedChunk
from app.services.rag_service import get_rag_service
from app.utils.exceptions import NoDocumentsError


class FakeRAGService:
    """Minimal stand-in implementing the surface the routes depend on."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self._count = 0
        self.documents: list[str] = []

    def document_count(self) -> int:
        return self._count

    def ingest_pdf(self, pdf_path: Path, original_filename: str, user_id: int) -> IngestionResult:
        self._count += 3
        if original_filename not in self.documents:
            self.documents.append(original_filename)
        return IngestionResult(filename=original_filename, pages=2, chunks_created=3)

    def list_documents(self, user_id: int) -> list[str]:
        return self.documents

    def delete_document(self, filename: str, user_id: int) -> None:
        if filename in self.documents:
            self.documents.remove(filename)
            self._count = max(0, self._count - 3)

    def ask(self, question: str, history=None, top_k=None, selected_document=None, user_id=None) -> RAGAnswer:
        if self._count == 0:
            raise NoDocumentsError("No documents have been indexed yet.")
        doc = Document(
            page_content="The document is about retrieval-augmented generation.",
            metadata={"source": "demo.pdf", "page": 0},
        )
        return RAGAnswer(
            answer="It is about RAG.",
            chunks=[RetrievedChunk(document=doc, score=0.91)],
            confidence=0.9,
        )


@pytest.fixture
def client() -> TestClient:
    app = create_app()
    fake = FakeRAGService()
    
    from app.api.routes import get_current_user
    from app.models.schemas import User
    mock_user = User(id=1, email="test@test.com", hashed_password="fake", username="testuser")
    
    app.dependency_overrides[get_rag_service] = lambda: fake
    app.dependency_overrides[get_current_user] = lambda: mock_user
    
    return TestClient(app)


def test_health(client: TestClient):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "healthy"
    assert "llm_provider" in body


def test_ask_before_upload_returns_conflict(client: TestClient):
    resp = client.post("/ask", json={"question": "What is this?"})
    assert resp.status_code == 409


def test_upload_rejects_unsupported_format(client: TestClient):
    resp = client.post(
        "/upload-pdf",
        files={"file": ("image.png", b"fake png data", "image/png")},
    )
    assert resp.status_code == 400


def test_upload_then_ask_flow(client: TestClient):
    up = client.post(
        "/upload-pdf",
        files={"file": ("demo.pdf", b"%PDF-1.4 fake", "application/pdf")},
    )
    assert up.status_code == 201
    assert up.json()["chunks_created"] == 3

    ask = client.post("/ask", json={"question": "What is this document about?"})
    assert ask.status_code == 200
    body = ask.json()
    assert body["answer"] == "It is about RAG."
    assert body["confidence"] == 0.9
    assert len(body["sources"]) == 1
    assert body["sources"][0]["source"] == "demo.pdf"
    assert body["sources"][0]["page"] == 0
    assert body["sources"][0]["score"] == 0.91
    assert body["sources"][0]["content"] == "The document is about retrieval-augmented generation."


def test_ask_validation_rejects_empty_question(client: TestClient):
    resp = client.post("/ask", json={"question": ""})
    assert resp.status_code == 422


def test_list_and_delete_documents_flow(client: TestClient):
    # 1. Initially, no documents are indexed
    resp = client.get("/documents")
    assert resp.status_code == 200
    assert resp.json() == {"documents": []}

    # 2. Upload a document
    up = client.post(
        "/upload-pdf",
        files={"file": ("demo.pdf", b"%PDF-1.4 fake", "application/pdf")},
    )
    assert up.status_code == 201

    # 3. Verify it is listed
    resp = client.get("/documents")
    assert resp.status_code == 200
    assert resp.json() == {"documents": ["demo.pdf"]}

    # 4. Delete the document
    del_resp = client.delete("/documents/demo.pdf")
    assert del_resp.status_code == 200
    assert del_resp.json() == {
        "message": "Document deleted successfully",
        "filename": "demo.pdf",
    }

    # 5. Verify it is gone
    resp = client.get("/documents")
    assert resp.status_code == 200
    assert resp.json() == {"documents": []}


def test_ask_with_history_succeeds(client: TestClient):
    client.post(
        "/upload-pdf",
        files={"file": ("demo.pdf", b"%PDF-1.4 fake", "application/pdf")},
    )
    resp = client.post(
        "/ask",
        json={
            "question": "What about that?",
            "history": [{"role": "user", "content": "Tell me about RAG."}]
        }
    )
    assert resp.status_code == 200
    assert resp.json()["answer"] == "It is about RAG."


def test_ask_with_selected_document_succeeds(client: TestClient):
    client.post(
        "/upload-pdf",
        files={"file": ("demo.pdf", b"%PDF-1.4 fake", "application/pdf")},
    )
    resp = client.post(
        "/ask",
        json={
            "question": "What is this about?",
            "selected_document": "demo.pdf"
        }
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["answer"] == "It is about RAG."
    assert body["sources"][0]["source"] == "demo.pdf"
