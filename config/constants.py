"""
TITAN Constants
"""

from pathlib import Path

# ==========================================
# Project
# ==========================================

PROJECT_NAME = "TITAN"
PROJECT_TITLE = "TITAN Stock Analysis Engine"
VERSION = "1.0.0"

# ==========================================
# Directory
# ==========================================

ROOT_DIR = Path(__file__).resolve().parent.parent

DATA_DIR = ROOT_DIR / "data"
OUTPUT_DIR = ROOT_DIR / "output"
LOG_DIR = ROOT_DIR / "logs"
CACHE_DIR = ROOT_DIR / "cache"

# Create directory automatically
for directory in (
    DATA_DIR,
    OUTPUT_DIR,
    LOG_DIR,
    CACHE_DIR,
):
    directory.mkdir(parents=True, exist_ok=True)