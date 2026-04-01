"""Generic location filter must work for any city, not just NYC."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "drafter"))


def test_matching_city_accepted():
    from draft_applications import is_allowed_location
    assert is_allowed_location(
        {"location": "New York, NY"},
        {"location_preference": "New York, NY"}
    ) is True


def test_different_city_rejected():
    from draft_applications import is_allowed_location
    assert is_allowed_location(
        {"location": "Chicago, IL"},
        {"location_preference": "New York, NY"}
    ) is False


def test_austin_profile_accepts_austin():
    from draft_applications import is_allowed_location
    assert is_allowed_location(
        {"location": "Austin, TX"},
        {"location_preference": "Austin, TX"}
    ) is True


def test_austin_profile_rejects_nyc():
    from draft_applications import is_allowed_location
    assert is_allowed_location(
        {"location": "New York, NY"},
        {"location_preference": "Austin, TX"}
    ) is False


def test_remote_profile_accepts_any_city():
    from draft_applications import is_allowed_location
    assert is_allowed_location(
        {"location": "Dallas, TX"},
        {"location_preference": "Remote"}
    ) is True


def test_blank_job_location_accepted():
    from draft_applications import is_allowed_location
    assert is_allowed_location(
        {"location": ""},
        {"location_preference": "New York, NY"}
    ) is True


def test_no_profile_preference_accepts_any():
    from draft_applications import is_allowed_location
    assert is_allowed_location(
        {"location": "Denver, CO"},
        {}
    ) is True


def test_case_insensitive_match():
    from draft_applications import is_allowed_location
    assert is_allowed_location(
        {"location": "NEW YORK, NY"},
        {"location_preference": "New York, NY"}
    ) is True
