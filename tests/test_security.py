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


# ── Path traversal tests ──────────────────────────────────────────────────

def test_valid_date_passes():
    from server import _validate_date_str
    _validate_date_str("2026-03-31")  # must not raise


def test_path_traversal_rejected():
    from server import _validate_date_str
    with pytest.raises(ValueError):
        _validate_date_str("../../../etc/passwd")


def test_traversal_with_mixed_path():
    from server import _validate_date_str
    with pytest.raises(ValueError):
        _validate_date_str("2026-/../2026-03-31")


def test_empty_string_rejected():
    from server import _validate_date_str
    with pytest.raises(ValueError):
        _validate_date_str("")


def test_wrong_format_rejected():
    from server import _validate_date_str
    with pytest.raises(ValueError):
        _validate_date_str("31-03-2026")
