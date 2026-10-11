# PythonAnywhere Deployment Guide — v3.0

## One-time setup (or after major upgrade)

### Step 1 — Push latest code

From your local machine:
```bash
git add -A
git commit -m "v3.0 industry upgrade"
git push origin main
```

Then on PythonAnywhere **Bash console**:
```bash
cd ~/Resume_Analyzer
git pull origin main
```

---

### Step 2 — Install / update dependencies

```bash
pip3 install --user -r requirements.txt
```

If you see PyPDF2 or python-docx errors, install manually:
```bash
pip3 install --user PyPDF2==3.0.1 python-docx==1.1.0
```

---

### Step 3 — Initialise the database

```bash
cd ~/Resume_Analyzer
python3 -c "from app import app, db; app.app_context().__enter__(); db.create_all(); print('DB OK')"
```

---

### Step 4 — Fix WSGI configuration

1. Go to **Web** tab in PythonAnywhere dashboard
2. Click on the **WSGI configuration file** link under "Code"
3. **Delete all content** and paste the contents of `wsgi_config_pythonanywhere.py`
4. Click **Save**

---

### Step 5 — Fix Static Files mapping

In the **Web** tab, scroll to **Static files**. Remove ALL entries, then add exactly ONE:

| URL      | Directory                                    |
|----------|----------------------------------------------|
| /static/ | /home/sapandesai/Resume_Analyzer/static      |

⚠️ Do NOT add a mapping for `/` pointing to the project root — this causes PythonAnywhere to serve files instead of running Flask.

---

### Step 6 — Set Working Directory & Source Code

Under "Code" section in Web tab:

| Field              | Value                                  |
|--------------------|----------------------------------------|
| Source code        | /home/sapandesai/Resume_Analyzer       |
| Working directory  | /home/sapandesai/Resume_Analyzer       |

---

### Step 7 — Reload

Click the big green **Reload sapandesai.pythonanywhere.com** button.

Wait 10 seconds, then visit: **http://sapandesai.pythonanywhere.com**

---

## Troubleshooting

### Check error log first

Web tab → Log files → **Error log** → read the last 20 lines.

### Common errors and fixes

| Error | Fix |
|-------|-----|
| `ModuleNotFoundError: No module named 'flask'` | `pip3 install --user Flask==3.0.0` |
| `ModuleNotFoundError: No module named 'PyPDF2'` | `pip3 install --user PyPDF2==3.0.1` |
| `ModuleNotFoundError: No module named 'app'` | Check WSGI file path and `sys.path` entries |
| Still showing README.md | Wrong static file mapping — redo Step 5 |
| `No module named 'modules.jd_matcher'` | `git pull` didn't include new files |
| Database errors | Redo Step 3 |
| 500 on `/dashboard` | Check error log; usually a missing DB table — redo Step 3 |

### Verify all new modules are present

```bash
ls ~/Resume_Analyzer/modules/
# Should include: jd_matcher.py, ats_scorer.py, matcher.py, ...

ls ~/Resume_Analyzer/data/
# Should include: job_roles.json (25 roles), skills.json (300+ skills)
```

### Test the app from Bash console

```bash
cd ~/Resume_Analyzer
python3 -c "
from modules.matcher import SkillMatcher
m = SkillMatcher('data/job_roles.json')
print('Roles:', len(m.get_available_roles()))
from modules.jd_matcher import JDMatcher
jd = JDMatcher('data/skills.json')
print('Skills:', len(jd.all_skills))
from modules.ats_scorer import ATSScorer
print('ATS: OK')
print('All modules loaded successfully')
"
```

---

## New API endpoints in v3.0

After deployment, these new endpoints are live:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/match-jd` | POST | Match resume against custom JD text |
| `/api/ats-score` | POST | ATS compatibility score |
| `/api/top-roles` | POST | Top 5 role matches for a resume |
| `/api/roles?grouped=true` | GET | Roles grouped by category |

Test from browser: `http://sapandesai.pythonanywhere.com/api/roles?grouped=true`

---

## Emergency reset

If nothing works:
1. Delete the web app in PythonAnywhere
2. Create new: Flask → Python 3.12 → path `/home/sapandesai/Resume_Analyzer/app.py`
3. Redo Steps 4–7 above
