"""Tests for security fixes: .env injection and path traversal."""
import pytest


# ── .env injection tests ──────────────────────────────────────────────────

def test_sanitize_strips_newline():
    from setup_handler import _sanitize_env_val
    assert _sanitize_env_val("mykey\nOPENAI_API_KEY=stolen") == "mykeyOPENAI_API_KEY=stolen"


def test_sanitize_strips_carriage_return():
    from setup_handler import _sanitize_env_val
    assert _sanitize_env_val("foo\rbar") == "foobar"


def test_sanitize_strips_null_byte():
    from setup_handler import _sanitize_env_val
    assert _sanitize_env_val("foo\x00bar") == "foobar"


def test_sanitize_leaves_clean_value_unchanged():
    from setup_handler import _sanitize_env_val
    assert _sanitize_env_val("sk-abc123XYZ") == "sk-abc123XYZ"


def test_sanitize_handles_non_string():
    from setup_handler import _sanitize_env_val
    assert _sanitize_env_val(None) == "None"
