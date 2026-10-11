"""
WSGI Configuration for PythonAnywhere — AI Resume Analyzer v3.0
================================================================
INSTRUCTIONS:
  1. In PythonAnywhere Web tab → "Code" section → click "WSGI configuration file"
  2. DELETE all existing content
  3. Paste this entire file and Save
  4. In "Static files" section keep ONLY:
       URL: /static/    →  Directory: /home/sapandesai/Resume_Analyzer/static
     (delete any mapping at "/" or pointing at the project root)
  5. Set Working directory: /home/sapandesai/Resume_Analyzer
  6. Click the green Reload button
"""

import sys
import os

# ── Python packages (adjust Python version if yours differs) ──────────────
sys.path.insert(0, '/home/sapandesai/.local/lib/python3.13/site-packages')
sys.path.insert(0, '/home/sapandesai/.local/lib/python3.12/site-packages')

# ── Project root ─────────────────────────────────────────────────────────
PROJECT_ROOT = '/home/sapandesai/Resume_Analyzer'
sys.path.insert(0, PROJECT_ROOT)

# ── Working directory (critical — ensures data/ and uploads/ resolve correctly)
os.chdir(PROJECT_ROOT)

# ── Environment variables (set here if not using a .env file on PythonAnywhere)
# os.environ.setdefault('SECRET_KEY', 'change-me-in-production')
# os.environ.setdefault('DATABASE_URL', '')   # leave blank for SQLite default

# ── Import Flask application ─────────────────────────────────────────────
from app import app as application  # noqa: F401

# PythonAnywhere requires the variable to be named `application`
