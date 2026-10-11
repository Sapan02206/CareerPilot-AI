# Runtime Test Checklist — AI Resume Analyzer v3.0

**Status: ALL ITEMS BLOCKED — Python not installed**  
Complete SETUP.md steps first, then execute each test below.

---

## How to use this checklist

For each test:
1. Perform the described action
2. Compare actual result to Expected Result
3. Mark PASS / FAIL in the Status column

---

## Pre-flight: Automated Tests

Run these before any manual testing.

```powershell
cd d:\Resume_Analyzer
.venv\Scripts\Activate.ps1
python -m pytest tests/smoke_test.py -v
python -m pytest tests/test_jd_matcher.py -v
```

Both must show all tests PASSING before continuing to manual tests.

---

## A — Application Startup

### A1: Flask starts without errors

**Action:** `python app.py`

**Expected output (contains):**
```
 * Serving Flask app 'app'
 * Debug mode: on
 * Running on http://0.0.0.0:5000
```

**Acceptable warnings (non-fatal):**
- `Info: spaCy not installed. Using pattern matching only.`
- `⚠️  Kaggle datasets not loaded: ...`

**FAIL conditions:**
- Any `ImportError` or `ModuleNotFoundError`
- `KeyError` or `AttributeError` during startup
- Flask does not start (no "Running on" line)
- Port 5000 already in use → change to `app.run(port=5001)` temporarily

**Status:** ☐ PASS / ☐ FAIL

---

### A2: Database tables auto-created

**Action:** After `python app.py` starts, check instance/ directory.

**Expected:** File `d:\Resume_Analyzer\instance\resume_analyzer.db` exists.

```powershell
Test-Path "d:\Resume_Analyzer\instance\resume_analyzer.db"
# Expected: True
```

**FAIL condition:** File does not exist after startup.

**Status:** ☐ PASS / ☐ FAIL

---

### A3: All 7 tables created

**Action:** In Python (separate terminal, venv active):
```python
from app import app, db
from sqlalchemy import inspect
with app.app_context():
    tables = inspect(db.engine).get_table_names()
    print(sorted(tables))
```

**Expected:**
```
['job_roles', 'readiness_snapshots', 'resumes', 'skills', 'user_projects', 'user_sessions', 'users']
```

**FAIL condition:** Any table is missing.

**Status:** ☐ PASS / ☐ FAIL

---

## B — Homepage

### B1: Homepage loads

**Action:** Open browser → `http://localhost:5000`

**Expected:**
- Page title: "AI Resume Analyzer — Industry Grade"
- Navbar visible with "Dashboard" and "Demo" links
- Hero section with "Analyze. Match. Get Hired." heading
- Stats bar showing "25+ Job Roles", "300+ Skills", "6 ATS Factors"
- Two tabs: "Match by Role" | "Match by Job Description"
- Role dropdown (tab 1) is populated with grouped `<optgroup>` sections
- ATS compatibility check card visible below the main form

**FAIL conditions:**
- Blank page or 500 error
- Role dropdown is empty
- Missing tabs
- CSS not loading (unstyled raw HTML)

**Status:** ☐ PASS / ☐ FAIL

---

### B2: Role dropdown has 25+ entries grouped by category

**Action:** Click the "Target Job Role" dropdown on the homepage.

**Expected:**
- Groups present: "Blockchain", "Data & AI", "Design", "Game Development",
  "Infrastructure", "Mobile", "Product", "Quality Assurance",
  "Security", "Systems", "Web Development"
- At least 25 individual role options total

**FAIL condition:** Fewer than 25 roles, or no `<optgroup>` grouping.

**Status:** ☐ PASS / ☐ FAIL

---

### B3: /api/roles endpoint

**Action:** `http://localhost:5000/api/roles`

**Expected JSON:**
```json
{"roles": ["AI Engineer", "Android Developer", ...]}
```
List has 25+ items.

**Status:** ☐ PASS / ☐ FAIL

---

### B4: /api/roles grouped

**Action:** `http://localhost:5000/api/roles?grouped=true`

**Expected JSON:**
```json
{"Blockchain": ["Blockchain Developer"], "Data & AI": [...], ...}
```

**Status:** ☐ PASS / ☐ FAIL

---

## C — Resume Upload (Role-Based Flow)

### C1: File validation — wrong format rejected

**Action:** Try to upload a `.txt` file via the homepage form.

**Expected:** Browser-side validation triggers before submit. Alert: "Only PDF and DOCX files are supported". File input cleared.

**FAIL condition:** File accepted, or no validation message.

**Status:** ☐ PASS / ☐ FAIL

---

### C2: File validation — oversized file rejected

**Action:** Try to upload any file >16 MB.

**Expected:** Alert: "File too large — max 16 MB". File input cleared.

**Status:** ☐ PASS / ☐ FAIL

---

### C3: No role selected — form prevents submission

**Action:** Select a PDF file but leave role dropdown on "Select a job role...". Click Analyze.

**Expected:** Browser HTML5 validation prevents form submission. Dropdown highlighted as required.

**Status:** ☐ PASS / ☐ FAIL

---

## D — PDF Parsing

**Prerequisite:** Have a real PDF resume file available.  
If you don't have one, create a minimal one for testing:

```
Save this text as a .txt, then use Word or LibreOffice to export as PDF:

John Smith | john@example.com | github.com/johnsmith
Senior Python Developer | 5 years experience

SKILLS
Python, Django, PostgreSQL, Docker, Git, REST API, Linux

EXPERIENCE
Backend Developer at TechCorp (2020-2024)
- Developed REST APIs using Python and Django
- Managed PostgreSQL databases, optimised queries by 30%
- Deployed applications with Docker and CI/CD pipelines
- Collaborated in Agile team of 8 engineers

EDUCATION
BSc Computer Science, University of Mumbai, 2020
```

### D1: PDF uploads and redirects to dashboard

**Action:** Upload the PDF resume. Select "Backend Developer". Click "Analyze Resume".

**Expected:**
- Loading overlay appears briefly
- Browser redirects to `/career-dashboard`
- Dashboard page loads with the gradient header visible
- Score ring starts animating

**FAIL conditions:**
- 400 or 500 error JSON response visible
- "Failed to extract text from resume" error
- No redirect — stays on homepage

**Status:** ☐ PASS / ☐ FAIL

---

### D2: PDF text extraction produces non-empty text

**Action:** In Flask logs (terminal running `python app.py`), look for startup output.

**Expected (no errors in logs during upload):**
No `Error extracting text:` lines in the terminal.

**Status:** ☐ PASS / ☐ FAIL

---

## E — DOCX Parsing

### E1: DOCX uploads and processes correctly

**Action:** Save the test resume text as a `.docx` file using Word or LibreOffice. Upload it with role "Backend Developer".

**Expected:** Same as D1 — redirect to dashboard, scores appear.

**FAIL condition:** "Failed to extract text" error, or score of 0% for a resume that clearly has skills.

**Status:** ☐ PASS / ☐ FAIL

---

## F — Skill Extraction

### F1: Expected skills are extracted from test resume

**Action:** After uploading the test resume (PDF or DOCX), check the dashboard.

**Expected in "Your Strengths" section:**
At minimum Python, Django, PostgreSQL, Docker, Git, REST API should appear.

**FAIL condition:** Skills section shows "No matched skills detected" when the resume clearly mentions Python, Django etc.

**Status:** ☐ PASS / ☐ FAIL

---

### F2: Alias normalisation works

**Action:** Create a resume that uses "JS" instead of "JavaScript", "k8s" instead of "Kubernetes", "Postgres" instead of "PostgreSQL". Upload against "Full Stack Developer".

**Expected:** The normalised canonical names appear in the dashboard (JavaScript, Kubernetes, PostgreSQL), not the abbreviations.

**Status:** ☐ PASS / ☐ FAIL

---

## G — Job-Role Matching

### G1: Match score is non-zero for a skilled resume

**Action:** Upload the test resume (Python, Django, PostgreSQL, Docker, Git) against "Backend Developer".

**Expected:**
- Skill Match score > 50% (resume has Python, Django, PostgreSQL, Git — all are required for Backend Developer)
- `matched_required` section shows those skills in green badges
- `missing_required` shows what's genuinely missing

**FAIL condition:**
- Match score = 0%
- All skills show as missing when resume clearly has them

**Status:** ☐ PASS / ☐ FAIL

---

### G2: Missing skills section is accurate

**Action:** Same upload as G1.

**Expected for Backend Developer required skills:** `["Python", "SQL", "REST API", "Git", "Linux", "Node.js"]`
Resume has Python, REST API, Git — so missing should include SQL, Linux, Node.js (at minimum).

**Status:** ☐ PASS / ☐ FAIL

---

### G3: /compare-all returns rankings

**Action:** Upload resume to `POST /compare-all` (use Postman or curl):
```
POST http://localhost:5000/compare-all
Content-Type: multipart/form-data
resume: [your test PDF]
```

**Expected:**
```json
{
  "extracted_skills": ["Python", "Django", ...],
  "role_matches": [
    {"role_name": "Backend Developer", "match_score": 70.5, ...},
    {"role_name": "Full Stack Developer", "match_score": 45.2, ...},
    ...
  ]
}
```
`role_matches` has 25 entries, sorted descending by score. First entry has `"top_match": true`.

**Status:** ☐ PASS / ☐ FAIL

---

## H — Custom JD Matching (JD Tab)

### H1: JD matching flow (valid JD)

**Action:** On homepage, click "Match by Job Description" tab. Upload resume, paste a real JD with technical skills. Click "Match Against This JD".

**Sample JD to paste:**
```
We are hiring a Backend Engineer.
Requirements:
- 3+ years Python experience
- Django or Flask framework experience
- PostgreSQL database management
- Docker containerisation
- REST API development
- Git version control required
Preferred:
- Redis caching
- AWS cloud experience
- Kubernetes orchestration
```

**Expected:**
- Results panel appears below the form (no page redirect)
- Score circle shows a percentage (not 0%, not 100%)
- "Matched Required" badges visible (green)
- "Missing Required" badges visible (red)
- "Recommendations" section shows 1-3 items with titles and detail text

**FAIL conditions:**
- Page shows error alert
- Score shows exactly 100% or exactly 0%
- Results panel stays hidden
- Recommendations show blank/empty body text (P0-1 regression)

**Status:** ☐ PASS / ☐ FAIL

---

## I — Empty JD (P0-2 Case A)

### I1: Empty JD shows error, not 100% score

**Action:** JD tab → upload resume → leave JD textarea completely empty → click "Match Against This JD".

**Expected:** Browser alert fires: "Please paste a job description first". Form does NOT submit.

**Status:** ☐ PASS / ☐ FAIL

---

### I2: Empty JD sent via API returns 0% with status

**Action:**
```powershell
# Using curl (available if Git is installed)
curl -X POST http://localhost:5000/api/match-jd -F "jd_text= " -F "resume_text=Python developer with 3 years experience"
```

**Expected JSON:**
```json
{
  "jd_match": {
    "analysis_status": "jd_empty",
    "match_score": 0.0,
    "recommendations": [{"title": "Job description could not be analysed", "detail": "..."}]
  }
}
```

**FAIL condition:** `match_score` is 100.0 or `analysis_status` is "ok".

**Status:** ☐ PASS / ☐ FAIL

---

## J — Very Short JD (P0-2 Case B)

### J1: Short JD returns 0% with status

**Action:**
```powershell
curl -X POST http://localhost:5000/api/match-jd -F "jd_text=hire developer" -F "resume_text=Python developer"
```

**Expected:** `analysis_status` is `"jd_too_short"`, `match_score` is `0.0`.

**Status:** ☐ PASS / ☐ FAIL

---

## K — JD With No Recognizable Skills (P0-2 Case C)

### K1: Generic JD with no tech skills returns 0%

**Action:** Paste this JD in the JD tab:
```
We are looking for a passionate and driven individual to join our growing
organisation. The ideal candidate will thrive in a fast-paced environment
and bring creativity and enthusiasm. Apply today and become part of our
journey toward excellence and innovation in the marketplace.
```

**Expected:** Score is 0%. Analysis status is `"no_skills_detected"`. Recommendation explains that no skills were found.

**FAIL condition:** Score is any non-zero value, especially 100%.

**Status:** ☐ PASS / ☐ FAIL

---

## L — JD With Only Soft Skills (P0-2 Case D)

### L1: Soft-skills-only JD returns low score with warning

**Action:** Paste this JD:
```
Requirements: Excellent communication skills. Strong leadership and problem
solving abilities. Team collaboration required. Time management essential.
Adaptability and creativity valued. Project management experience needed.
Agile methodology familiarity preferred.
```

**Expected:**
- `analysis_status` is `"only_soft_skills"` (or `"ok"` with a very low score)
- `match_score` is <= 50
- NOT 100%

**FAIL condition:** Score is 100%.

**Status:** ☐ PASS / ☐ FAIL

---

## M — Valid JD (P0-2 Case E)

### M1: Normal JD with tech skills scores correctly

**Action:** Use the same JD from test H1 (Backend Engineer with Python, Django, PostgreSQL etc.).

**Expected:**
- `analysis_status` is `"ok"`
- `match_score` is between 1 and 99 (for a partial-match resume)
- `jd_skills.total` > 0
- `resume_match.matched_required` is a non-empty list (if resume has matching skills)

**Status:** ☐ PASS / ☐ FAIL

---

## N — ATS Scoring

### N1: ATS check on homepage

**Action:** Upload a resume using the role-based form (tab 1). After it's loaded in the browser, click "Check ATS" button.

**Expected:**
- Results panel appears with:
  - Letter grade (A/B/C/D/F)
  - Percentage score (e.g., "67.3%")
  - Grade label (e.g., "Good — minor improvements recommended")
  - Six breakdown bars (keyword_match, section_structure, contact_info, quantification, action_verbs, formatting)
  - At least one improvement tip

**FAIL conditions:**
- "No resume provided" error
- Empty results panel
- Score shows NaN or undefined

**Status:** ☐ PASS / ☐ FAIL

---

### N2: ATS score breakdown weights sum to 100%

**Action:** Same as N1. Read the six "weight" labels from the breakdown cards.

**Expected:** keyword_match=35%, section_structure=20%, quantification=15%, contact_info=10%, action_verbs=10%, formatting=10%. These add to 100%.

**Status:** ☐ PASS / ☐ FAIL

---

### N3: ATS score via API

**Action:**
```powershell
curl -X POST http://localhost:5000/api/ats-score -F "resume_text=John Smith john@example.com. SKILLS: Python Django. EXPERIENCE: Developed REST APIs. Built 3 services serving 10k users."
```

**Expected JSON:**
```json
{
  "total_score": <number 0-100>,
  "grade": "A"|"B"|"C"|"D"|"F",
  "grade_label": "...",
  "breakdown": {...},
  "improvement_tips": [...],
  "word_count": <number>
}
```

**Status:** ☐ PASS / ☐ FAIL

---

## O — Dashboard

### O1: Dashboard loads readiness scores

**Action:** After uploading resume (test D1 or E1), dashboard redirects. Wait for scores to render.

**Expected:**
- Score ring animates to a percentage value
- "Target Role:" shows the selected role
- Status pill shows one of: "🎉 Ready to Apply!", "👍 Almost There", "📚 Keep Learning", "🚀 Getting Started"
- Three sub-score boxes (Skill Match, Experience, Evidence) show percentages
- Radar chart renders with purple polygon
- Breakdown bars animate to correct widths

**FAIL conditions:**
- Dashboard stuck on loading spinner indefinitely
- Scores show "--" (not replaced)
- Console errors (open DevTools → Console)

**Status:** ☐ PASS / ☐ FAIL

---

### O2: Dashboard handles returning user (no resume in session)

**Action:** After O1, open a new browser tab to `http://localhost:5000/career-dashboard`.

**Expected:** Dashboard loads from the cached ReadinessSnapshot — scores reappear. ATS card is NOT shown (only shown on first upload).

**FAIL condition:** Redirects to homepage with "No resume data found".

**Status:** ☐ PASS / ☐ FAIL

---

## P — Recommendations

### P1: Recommendations render with title and body text (P0-1 test)

**Action:** On the dashboard, scroll to "Your Next Steps" card.

**Expected:**
- At least 1 recommendation card visible
- Each card shows:
  - A numbered circle (priority number)
  - A bold title line
  - Body text underneath (the `detail` field)
  - A badge showing the recommendation type

**FAIL condition:**
- Cards show only the title with nothing below (means `detail` key is still `description`)
- Empty "Your Next Steps" section

**Status:** ☐ PASS / ☐ FAIL

---

### P2: Recommendations match the skill gap

**Action:** Upload a resume with minimal skills (e.g., only "Python"). Target "Backend Developer" (requires Python, SQL, Node.js, Git, Linux, REST API).

**Expected:**
- Priority 1 recommendations reference missing required skills like "Learn SQL", "Learn Node.js"
- Body text says something like "[Skill] is a required skill for this role. Focus on this first."

**Status:** ☐ PASS / ☐ FAIL

---

## Q — Project / Evidence Scoring

### Q1: Add a project via modal

**Action:** On dashboard, click "Add Project". Fill in:
- Title: "Django REST API"
- Skills Used: "Python, Django, PostgreSQL, REST API"
- Project URL: "https://github.com/test/test"
- Click "Add Project"

**Expected:**
- Modal closes
- Toast notification: "Project added! Recalculating your score..."
- Project card appears in "Portfolio Projects" section showing title, skills, URL badge
- Evidence Score increases from 0% to ~35% (1 project = 25pts + 10pts for URL)
- Overall Score increases slightly

**FAIL conditions:**
- Modal doesn't close
- Project doesn't appear
- Evidence score stays at 0%

**Status:** ☐ PASS / ☐ FAIL

---

### Q2: Delete a project

**Action:** Click the trash icon on the project card added in Q1.

**Expected:**
- Confirmation dialog appears
- After confirming, project card disappears
- Evidence Score drops back to 0%
- Overall Score decreases

**Status:** ☐ PASS / ☐ FAIL

---

### Q3: Evidence score formula is correct

**Action:** Add two projects both using required skills, one with URL, one without.

**Expected Evidence Score:**
- Project 1 (no URL): 25 pts
- Project 2 (with URL): 25 + 10 = 35 pts
- Total: min(50 + 10, 100) = 60%

Tolerance: ± 5% (actual score depends on which skills overlap with required skills)

**Status:** ☐ PASS / ☐ FAIL

---

## R — Readiness Score

### R1: Overall score formula is correct

**Action:** Note the three sub-scores from the dashboard:
- Skill Match = S%
- Experience = E%
- Evidence = V%

**Expected:**
Overall Score = (S × 0.50) + (E × 0.30) + (V × 0.20)

Calculate manually and compare. Allow ±0.1% for float rounding.

**Status:** ☐ PASS / ☐ FAIL

---

### R2: Experience score increases for a senior resume

**Action:** Upload a resume that explicitly states "5 years of Python experience" and "3 years of Django". Target "Backend Developer".

**Expected:** Experience score > 0% (the experience extractor found the explicit year patterns).

**FAIL condition:** Experience score stays at 0% despite explicit year mentions in resume text.

**Status:** ☐ PASS / ☐ FAIL

---

## S — Historical Snapshots / Progress

### S1: Progress timeline appears after multiple visits

**Action:** Visit the dashboard 3 times (each visit creates a new snapshot). Check "Your Progress" card.

**Expected:**
- Timeline table shows 3+ rows
- Each row has a date, progress bar, and score
- "Progress Over Time" chart renders with at least 1 line (requires 2+ data points)
- If improvement > 0, a green "+" banner appears above the timeline

**FAIL condition:**
- Timeline always shows "No progress data yet"
- Chart doesn't render (canvas stays blank)

**Status:** ☐ PASS / ☐ FAIL

---

### S2: /api/progress returns timeline

**Action:** `http://localhost:5000/api/progress`

**Expected:**
```json
{
  "timeline": [
    {"date": "2026-...", "overall_score": 45.0, ...},
    ...
  ],
  "total_snapshots": <N>,
  "improvement": <float>,
  "target_role": "Backend Developer"
}
```

**Status:** ☐ PASS / ☐ FAIL

---

## T — Database Operations

### T1: Projects persist across browser sessions

**Action:** Add a project (Q1). Close the browser completely. Reopen and visit `/career-dashboard`.

**Expected:** The project from Q1 still appears in the portfolio section.

**Note:** This depends on Flask session cookie persisting. The `PERMANENT_SESSION_LIFETIME = 30 days` is set in config.

**Status:** ☐ PASS / ☐ FAIL

---

### T2: /api/history returns records

**Action:** `http://localhost:5000/api/history`

**Expected:**
```json
{
  "total": <N>,
  "resumes": [...]
}
```

**Note:** The `resumes` table is only populated by the demo/Kaggle route. May be empty if only using the main upload flow. An empty list `[]` with `total: 0` is a PASS.

**Status:** ☐ PASS / ☐ FAIL

---

### T3: Delete a project — DB record removed

**Action:** After Q2 (delete project), verify via API:

```
GET http://localhost:5000/api/projects
```

**Expected:** The deleted project no longer appears in the `projects` array.

**Status:** ☐ PASS / ☐ FAIL

---

## Summary Table (Fill in after testing)

| ID | Test | Status | Notes |
|----|------|--------|-------|
| A1 | Flask startup | ☐ | |
| A2 | SQLite DB created | ☐ | |
| A3 | 7 tables exist | ☐ | |
| B1 | Homepage loads | ☐ | |
| B2 | Role dropdown 25+ | ☐ | |
| B3 | /api/roles | ☐ | |
| B4 | /api/roles grouped | ☐ | |
| C1 | Wrong format rejected | ☐ | |
| C2 | Oversized rejected | ☐ | |
| C3 | No role → blocked | ☐ | |
| D1 | PDF upload + redirect | ☐ | |
| D2 | No extraction errors | ☐ | |
| E1 | DOCX upload | ☐ | |
| F1 | Skills extracted | ☐ | |
| F2 | Alias normalisation | ☐ | |
| G1 | Match score non-zero | ☐ | |
| G2 | Missing skills accurate | ☐ | |
| G3 | /compare-all | ☐ | |
| H1 | JD matching valid JD | ☐ | |
| I1 | Empty JD → browser block | ☐ | |
| I2 | Empty JD → API 0% | ☐ | |
| J1 | Short JD → 0% | ☐ | |
| K1 | No-skills JD → 0% | ☐ | |
| L1 | Soft-only JD → low | ☐ | |
| M1 | Valid JD → ok status | ☐ | |
| N1 | ATS check on page | ☐ | |
| N2 | ATS weights sum 100% | ☐ | |
| N3 | ATS via API | ☐ | |
| O1 | Dashboard loads scores | ☐ | |
| O2 | Returning user loads | ☐ | |
| P1 | Recs have detail text | ☐ | |
| P2 | Recs match skill gap | ☐ | |
| Q1 | Add project | ☐ | |
| Q2 | Delete project | ☐ | |
| Q3 | Evidence formula | ☐ | |
| R1 | Readiness formula | ☐ | |
| R2 | Experience from text | ☐ | |
| S1 | Progress timeline | ☐ | |
| S2 | /api/progress | ☐ | |
| T1 | Projects persist | ☐ | |
| T2 | /api/history | ☐ | |
| T3 | Deleted project gone | ☐ | |

---

## Known Issues Before Testing

| Issue | File | Severity | Status |
|-------|------|----------|--------|
| `python-dateutil` not in requirements.txt | requirements.txt | P1 | **FIXED** (added 2.9.0) |
| Recommendation `description` vs `detail` field mismatch | readiness_calculator.py | P0 | **FIXED** |
| JD scorer returns 100% for empty/unrecognised JDs | jd_matcher.py | P0 | **FIXED** |
| db.create_all() only under `__main__` | app.py | P1 | **FIXED** |

---

## Blocking Requirements Summary

To execute any test in this checklist, you need:

1. **Python 3.10–3.12** installed from python.org — NOT the Windows Store stub
2. `.venv` virtual environment created and activated
3. `pip install -r requirements.txt` completed without errors
4. `.env` file created with a `SECRET_KEY` set
5. Flask app started with `python app.py` (port 5000 free)
6. A PDF or DOCX resume file for upload tests D1–F2

Estimated setup time: 15–20 minutes for a clean Windows machine.
