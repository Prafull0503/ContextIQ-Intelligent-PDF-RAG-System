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

    def document_count(self) -> int:
        return self._count

    def ingest_pdf(self, pdf_path: Path, original_filename: str) -> IngestionResult:
        self._count += 3
        return IngestionResult(filename=original_filename, pages=2, chunks_created=3)

    def ask(self, question: str, top_k=None) -> RAGAnswer:
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
    app.dependency_overrides[get_rag_service] = lambda: fake
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


def test_upload_rejects_non_pdf(client: TestClient):
    resp = client.post(
        "/upload-pdf",
        files={"file": ("notes.txt", b"hello", "text/plain")},
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
    # Response is intentionally answer-only — no sources / confidence exposed.
    assert "sources" not in body
    assert "confidence" not in body


def test_ask_validation_rejects_empty_question(client: TestClient):
    resp = client.post("/ask", json={"question": ""})
    assert resp.status_code == 422
