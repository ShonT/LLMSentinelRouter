"""
Tests for the FastAPI server.
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock

from sentinelrouter.sentinelrouter.server import app
from sentinelrouter.sentinelrouter.clients import LLMResponse


@pytest.fixture
def client():
    """Test client for FastAPI."""
    return TestClient(app)


def test_health_endpoint(client):
    """Test the health endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "sentinelrouter"


def test_metrics_endpoint(client):
    """Test the metrics endpoint (placeholder)."""
    response = client.get("/metrics")
    assert response.status_code == 200
    data = response.json()
    assert "requests_total" in data
    assert "cost_total" in data


def test_audit_endpoint(client):
    """Test the audit endpoint (placeholder)."""
    response = client.get("/audit/some_session")
    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == "some_session"
    assert "decisions" in data


@patch("sentinelrouter.server.route_request")
def test_chat_completions_success(mock_route, client):
    """Test the chat completions endpoint with successful routing."""
    mock_response = LLMResponse(
        content="Test response",
        model="deepseek-chat",
        usage={"total_tokens": 10},
        cost=0.0001,
    )
    mock_route.return_value = {
        "model_used": "deepseek",
        "response": mock_response,
        "complexity_score": 0.3,
        "cost": 0.0001,
        "cycle_detected": False,
        "decision_reason": "complexity=0.300, threshold=0.700",
    }

    payload = {
        "model": "ignored",
        "messages": [{"role": "user", "content": "Hello"}],
        "temperature": 0.7,
        "session_id": "test_session_123",
    }
    response = client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["model"] == "deepseek-chat"
    assert data["choices"][0]["message"]["content"] == "Test response"
    # Check custom headers
    assert response.headers["X-Sentinel-Model-Used"] == "deepseek"
    assert response.headers["X-Sentinel-Cost"] == "0.0001"
    assert response.headers["X-Sentinel-Complexity-Score"] == "0.3"


@patch("sentinelrouter.server.route_request")
def test_chat_completions_budget_exceeded(mock_route, client):
    """Test that budget exceeded returns 429."""
    mock_route.side_effect = ValueError("Budget exceeded for session test_session.")

    payload = {
        "messages": [{"role": "user", "content": "Hello"}],
        "session_id": "test_session",
    }
    response = client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 429
    data = response.json()
    assert "detail" in data
    assert "Budget exceeded" in data["detail"]


@patch("sentinelrouter.server.route_request")
def test_chat_completions_no_session_id(mock_route, client):
    """Test that a session ID is generated when not provided."""
    mock_response = LLMResponse(
        content="Test",
        model="deepseek-chat",
        usage={},
        cost=0.0,
    )
    mock_route.return_value = {
        "model_used": "deepseek",
        "response": mock_response,
        "complexity_score": 0.5,
        "cost": 0.0,
        "cycle_detected": False,
        "decision_reason": "",
    }

    payload = {
        "messages": [{"role": "user", "content": "Hello"}],
    }
    response = client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 200
    # The route_request should have been called with a generated session ID
    call_kwargs = mock_route.call_args[1]
    assert "session_id" in call_kwargs
    assert call_kwargs["session_id"] is not None


if __name__ == "__main__":
    pytest.main([__file__])