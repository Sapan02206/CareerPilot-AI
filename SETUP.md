# Runtime Setup Guide — AI Resume Analyzer v3.0
# Windows (PowerShell)

---

## 0. Environment Assessment (Current State of This Machine)

Python is NOT installed on this machine.  
The PATH contains: Git, Node.js, .NET, npm — no Python interpreter.  
Windows Store Python stub exists at `C:\Users\HP\AppData\Local\Microsoft\WindowsApps\python.exe` — this is a redirect to the Store, not a real interpreter.

**All runtime tests are BLOCKED until Python is installed.**

---

## 1. Python Installation

### Required version
Python **3.10, 3.11, or 3.12** (64-bit).  
Do NOT use 3.13 — pandas 2.1.4 wheels are not available for 3.13.

### Install steps
1. Go to https://www.python.org/downloads/
2. Download **Python 3.12.x** (Windows installer 64-bit)
3. Run the installer
4. **CRITICAL**: Check "Add Python to PATH" on the first screen
5. Click "Install Now"
6. After install, open a NEW PowerShell window and verify:

```powershell
python --version
# Expected: Python 3.12.x

pip --version
# Expected: pip 24.x from C:\Users\HP\AppData\Local\Programs\Python\Python312\...
```

If `python` still opens the Store, disable the alias:
Settings → Apps → Advanced app settings → App execution aliases  
Turn OFF both "python.exe" and "python3.exe" toggles.

---

## 2. Virtual Environment

Always use a venv. Never install into the system Python.

```powershell
# Navigate to project root
cd d:\Resume_Analyzer

# Create virtual environment
python -m venv .venv

# Activate it
.venv\Scripts\Activate.ps1

# If activation is blocked by execution policy:
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
# Then retry the Activate command

# Confirm activation — prompt should show (.venv)
python --version
```

---

## 3. Dependency Installation

With the venv activated:

```powershell
cd d:\Resume_Analyzer

# Upgrade pip first (avoids legacy resolver issues)
python -m pip install --upgrade pip

# Install all dependencies
pip install -r requirements.txt
```

### What gets installed
| Package | Version | Purpose |
|---------|---------|---------|
| Flask | 3.0.0 | Web framework |
| Werkzeug | 3.0.1 | Flask dependency, file security |
| gunicorn | 21.2.0 | WSGI server (production) |
| Flask-SQLAlchemy | 3.1.1 | ORM / database |
| PyPDF2 | 3.0.1 | PDF text extraction |
| python-docx | 1.1.0 | DOCX text extraction |
| python-dotenv | 1.0.0 | .env file loading |
| python-dateutil | 2.9.0 | Date parsing in experience_extractor.py |
| pandas | 2.1.4 | Kaggle dataset processing |
| numpy | 1.26.2 | Numerical operations |
| pytest | (latest) | Test runner — install separately |

### Install pytest
```powershell
pip install pytest pytest-cov
```

### Optional dependencies (not required for core functionality)
```powershell
# spaCy — improves skill extraction accuracy (graceful fallback if absent)
pip install spacy
python -m spacy download en_core_web_sm

# scikit-learn — only needed for ML model training scripts
pip install scikit-learn==1.3.2
```

### Verify installation
```powershell
python -c "import flask; import sqlalchemy; import PyPDF2; import docx; import dateutil; print('All core imports OK')"
```

Expected output: `All core imports OK`

---

## 4. Environment Variables

```powershell
# Copy the example file
Copy-Item .env.example .env
```

Then open `.env` in any text editor and set:

```env
# Required
SECRET_KEY=change-this-to-a-random-string-at-least-32-chars

# Database — leave blank for SQLite (recommended for local dev)
DATABASE_URL=

# Upload folder — default is fine
UPLOAD_FOLDER=uploads
```

Generate a proper secret key:
```powershell
python -c "import secrets; print(secrets.token_hex(32))"
```
Copy the output into `SECRET_KEY=` in `.env`.

**DATABASE_URL**: Leave blank. The app falls back to SQLite at  
`d:\Resume_Analyzer\instance\resume_analyzer.db` automatically.

---

## 5. Database Initialisation

The database is now initialised automatically when the app starts  
(via `with app.app_context(): db.create_all()` at module level in `app.py`).

No manual step is required. However, to verify:

```powershell
# Confirm tables are created by importing the app module
python -c "
from app import app, db
with app.app_context():
    from sqlalchemy import inspect
    inspector = inspect(db.engine)
    tables = inspector.get_table_names()
    print('Tables created:', tables)
"
```

Expected output:
```
Tables created: ['job_roles', 'readiness_snapshots', 'resumes', 'skills', 'user_projects', 'user_sessions', 'users']
```

---

## 6. Running the Flask Application

```powershell
cd d:\Resume_Analyzer
.venv\Scripts\Activate.ps1
python app.py
```

Expected startup output:
```
Info: spaCy not installed. Using pattern matching only.
⚠️  Kaggle datasets not loaded: [No module named ... or file not found]
 * Serving Flask app 'app'
 * Debug mode: on
 * Running on http://0.0.0.0:5000
```

The Kaggle warning is expected and non-fatal. The app runs fully without it.

Open browser: **http://localhost:5000**

To stop: `Ctrl+C`

---

## 7. Running pytest

```powershell
cd d:\Resume_Analyzer
.venv\Scripts\Activate.ps1

# Run JD matcher tests (no Flask/DB needed — pure unit tests)
python -m pytest tests/test_jd_matcher.py -v

# Run all tests
python -m pytest tests/ -v

# Run with coverage report
python -m pytest tests/ -v --cov=modules --cov-report=term-missing
```

Expected for `test_jd_matcher.py`:
```
tests/test_jd_matcher.py::TestCaseA_EmptyJD::test_empty_string PASSED
tests/test_jd_matcher.py::TestCaseA_EmptyJD::test_whitespace_only PASSED
...
25 passed in X.Xs
```

---

## 8. Quick Smoke Test Script

Save as `tests/smoke_test.py` and run after setup to verify all modules load:

```python
# Run with: python tests/smoke_test.py
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

errors = []

def check(label, fn):
    try:
        fn()
        print(f"  OK  {label}")
    except Exception as e:
        print(f"  FAIL {label}: {e}")
        errors.append(label)

print("=== Smoke Test ===")
check("config import",       lambda: __import__('config'))
check("models import",       lambda: __import__('models'))
check("parser import",       lambda: __import__('modules.parser', fromlist=['ResumeParser']))
check("skill_extractor",     lambda: __import__('modules.skill_extractor', fromlist=['SkillExtractor']))
check("experience_extractor",lambda: __import__('modules.experience_extractor', fromlist=['ExperienceExtractor']))
check("matcher import",      lambda: __import__('modules.matcher', fromlist=['SkillMatcher']))
check("recommender import",  lambda: __import__('modules.recommender', fromlist=['SkillRecommender']))
check("readiness_calculator",lambda: __import__('modules.readiness_calculator', fromlist=['ReadinessCalculator']))
check("jd_matcher import",   lambda: __import__('modules.jd_matcher', fromlist=['JDMatcher']))
check("ats_scorer import",   lambda: __import__('modules.ats_scorer', fromlist=['ATSScorer']))
check("skills.json loads",   lambda: __import__('json').load(open('data/skills.json')))
check("job_roles.json loads",lambda: __import__('json').load(open('data/job_roles.json')))
check("SkillMatcher init",   lambda: (
    __import__('modules.matcher', fromlist=['SkillMatcher']).SkillMatcher('data/job_roles.json')
))
check("JDMatcher init",      lambda: (
    __import__('modules.jd_matcher', fromlist=['JDMatcher']).JDMatcher('data/skills.json')
))
check("25 roles loaded",     lambda: (
    lambda m: None if len(m.get_available_roles()) >= 25 else (_ for _ in ()).throw(AssertionError(f"Only {len(m.get_available_roles())} roles"))
)(__import__('modules.matcher', fromlist=['SkillMatcher']).SkillMatcher('data/job_roles.json')))

print(f"\n{'ALL PASS' if not errors else f'FAILED: {errors}'}")
sys.exit(1 if errors else 0)
```
