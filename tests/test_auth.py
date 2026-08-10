import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from app.application import create_app
from app.core.database import get_db
from app.core.config import get_settings
from app.models.schemas import User

# File-based SQLite for reliable test sessions
TEST_DATABASE_URL = "sqlite:///./data/test.db"
engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})

@pytest.fixture(name="db_session")
def db_session_fixture():
    """Create a temporary test database and clean up tables after test runs."""
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    SQLModel.metadata.drop_all(engine)

@pytest.fixture(name="client")
def client_fixture(db_session):
    """Override FastAPI database session dependency with in-memory SQLite session."""
    app = create_app()
    
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
            
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()

def test_signup_creates_user(client):
    """Verify posting valid credentials registers a user."""
    res = client.post("/auth/signup", json={"email": "test@test.com", "password": "mypassword", "username": "testuser"})
    assert res.status_code == 201
    data = res.json()
    assert data["email"] == "test@test.com"
    assert data["username"] == "testuser"
    assert "id" in data

def test_signup_fails_with_duplicate_email(client):
    """Verify registering duplicate email addresses is blocked."""
    client.post("/auth/signup", json={"email": "test@test.com", "password": "mypassword", "username": "testuser"})
    res2 = client.post("/auth/signup", json={"email": "test@test.com", "password": "mypassword2", "username": "testuser2"})
    assert res2.status_code == 400
    assert "already registered" in res2.json()["detail"]

def test_login_returns_token(client):
    """Verify valid credentials issue a valid JWT token."""
    client.post("/auth/signup", json={"email": "test@test.com", "password": "mypassword", "username": "testuser"})
    res = client.post("/auth/login", json={"email": "test@test.com", "password": "mypassword"})
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["username"] == "testuser"

def test_login_rejects_incorrect_password(client):
    """Verify authentication fails for wrong passwords."""
    client.post("/auth/signup", json={"email": "test@test.com", "password": "mypassword", "username": "testuser"})
    res = client.post("/auth/login", json={"email": "test@test.com", "password": "wrongpassword"})
    assert res.status_code == 401
    assert "Incorrect email" in res.json()["detail"]

def test_unauthenticated_requests_are_rejected(client):
    """Verify protected endpoints return 401 for requests without tokens."""
    res = client.get("/documents")
    assert res.status_code == 401
    assert "Not authenticated" in res.json()["detail"]
