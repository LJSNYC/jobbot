"""
pytest configuration — adds project subdirs to sys.path so tests can import
from scraper/, dashboard/, drafter/, setup/ without package structure.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scraper"))
sys.path.insert(0, str(ROOT / "drafter"))
sys.path.insert(0, str(ROOT / "setup"))
