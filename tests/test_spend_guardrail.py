"""Spend guardrail must fail CLOSED — return inf on any error, never 0.0."""
import pytest
from unittest.mock import patch, MagicMock


def test_fails_closed_on_network_error():
    with patch("draft_applications.requests.get") as mock_get:
        mock_get.side_effect = ConnectionError("network unreachable")
        from draft_applications import get_todays_spend
        result = get_todays_spend("sk-test-key")
    assert result == float('inf'), "Must return inf on exception, not 0.0"


def test_fails_closed_on_500_status():
    with patch("draft_applications.requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_get.return_value = mock_resp
        from draft_applications import get_todays_spend
        result = get_todays_spend("sk-test-key")
    assert result == float('inf'), "Must return inf on non-200 status"


def test_fails_closed_on_401_status():
    with patch("draft_applications.requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_get.return_value = mock_resp
        from draft_applications import get_todays_spend
        result = get_todays_spend("sk-test-key")
    assert result == float('inf'), "Must return inf on auth error"


def test_returns_dollars_on_success():
    with patch("draft_applications.requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"total_usage": 25}  # 25 cents = $0.25
        mock_get.return_value = mock_resp
        from draft_applications import get_todays_spend
        result = get_todays_spend("sk-test-key")
    assert result == pytest.approx(0.25)
