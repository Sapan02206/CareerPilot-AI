# Vercel Deployment Guide - CareerPilot AI

This document explains how to deploy CareerPilot AI to Vercel with PostgreSQL.

## Prerequisites

1. **Vercel Account**: Sign up at https://vercel.com
2. **Vercel CLI** (optional): `npm install -g vercel`
3. **GitHub Repository**: https://github.com/Sapan02206/CareerPilot-AI

## Critical Configuration

### Environment Variables

You **MUST** configure these in Vercel Project Settings → Environment Variables:

#### Required for Production:
```
DATABASE_URL=postgresql://user:password@host:5432/database
SECRET_KEY=your-secure-random-key-here
```

#### Optional (with defaults):
```
FLASK_ENV=production
REQUIRED_SKILL_WEIGHT=1.0
OPTIONAL_SKILL_WEIGHT=0.5
SKILLS_DATA_PATH=data/skills.json
JOB_ROLES_DATA_PATH=data/job_roles.json
```

### Vercel Postgres Setup

**Option 1: Vercel Postgres (Recommended)**

1. Go to your Vercel project dashboard
2. Navigate to **Storage** tab
3. Click **Create Database** → Select **Postgres**
4. Choose a plan (Hobby tier is free)
5. Vercel automatically sets `DATABASE_URL` environment variable
6. Database tables are created automatically on first deployment

**Option 2: External PostgreSQL**

You can use any PostgreSQL provider (Neon, Supabase, Railway, etc.):

1. Create a PostgreSQL database
2. Get the connection string (format: `postgresql://user:pass@host:port/dbname`)
3. Add it as `DATABASE_URL` in Vercel Environment Variables

## Deployment Methods

### Method 1: GitHub Integration (Recommended)

1. Push your code to GitHub: `git push origin main`
2. Visit https://vercel.com/new
3. Import your repository: `Sapan02206/CareerPilot-AI`
4. Vercel auto-detects `vercel.json` configuration
5. Add environment variables (see above)
6. Click **Deploy**

Auto-deployment: Every push to `main` triggers a new deployment.

### Method 2: Vercel CLI

```bash
# Install Vercel CLI
npm install -g vercel

# Login
vercel login

# Deploy from project directory
cd D:\Resume_Analyzer
vercel

# Follow prompts:
# - Link to existing project or create new one
# - Choose production deployment
```

### Method 3: Drag & Drop (Not Recommended)

Visit https://vercel.com/new and drag your project folder. **Note**: You'll need to manually configure environment variables.

## File Structure Changes for Vercel

The following minimal changes were made to support serverless deployment:

### 1. Upload Directory (`config.py`)
```python
# Automatically detects Vercel and uses /tmp/uploads instead of ./uploads
_default_upload = '/tmp/uploads' if os.environ.get('VERCEL') else 'uploads'
UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', _default_upload)
```

**Why**: Vercel's filesystem is read-only except `/tmp/`. Uploads are temporary and deleted after request completion.

### 2. Database Initialization (`app.py`)
```python
# Wrapped db.create_all() in try/except to prevent crashes
try:
    with app.app_context():
        db.create_all()
    print("✅ Database tables initialized successfully")
except Exception as e:
    print(f"❌ Database initialization failed: {e}")
    # App continues but database features won't work
```

**Why**: Provides clear error messages if DATABASE_URL is misconfigured.

### 3. Directory Creation (`app.py`)
```python
# Wrapped os.makedirs() in try/except
try:
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
except OSError as e:
    print(f"⚠️  Warning: Could not create upload folder: {e}")
```

**Why**: Prevents crashes on read-only filesystems.

### 4. PostgreSQL Driver (`requirements.txt`)
```
psycopg2-binary==2.9.9  # Required for PostgreSQL connections
```

**Why**: SQLAlchemy needs this to connect to PostgreSQL.

## Local Development Unchanged

All changes preserve local development behavior:
- SQLite still works locally: `sqlite:///resume_analyzer.db`
- Upload folder still `./uploads` on local machine
- All 165 tests pass unchanged
- No `.env` modifications needed

## Testing Deployment

After deployment, verify these endpoints:

1. **Health Check**: Visit `https://your-app.vercel.app/`
2. **Static Files**: Check CSS/JS load correctly
3. **Upload Resume**: Test the analyze feature
4. **Dashboard**: Verify database reads/writes work

## Database Initialization

Database tables are created automatically on first request. The `db.create_all()` call is idempotent (safe to run multiple times).

**If initialization fails**, check Vercel logs:
```bash
vercel logs your-app-name
```

Look for:
- `✅ Database tables initialized successfully` (success)
- `❌ Database initialization failed` (error - check DATABASE_URL)

## Known Limitations on Vercel

1. **File Uploads are Temporary**: Uploaded resumes are processed immediately and deleted. Files stored in `/tmp/` are cleared after request completion.

2. **Serverless Cold Starts**: First request after inactivity (~1-2 minutes) takes longer due to:
   - Loading pandas/numpy (~50MB)
   - Initializing ML models
   - Database connection

3. **Session Storage**: Flask sessions use signed cookies (4KB limit). Resume text is stored in session, which works for most resumes but may fail for very large documents (10+ pages).

   **If you encounter session issues**, consider:
   - Storing resume text in database instead of cookies
   - Using Redis or external session storage

4. **No Persistent Uploads Folder**: The `uploads/` directory doesn't persist between deployments. Current design handles this correctly (immediate cleanup).

## Troubleshooting

### Error: "Database initialization failed"
- **Cause**: Missing or incorrect `DATABASE_URL`
- **Fix**: Add `DATABASE_URL` in Vercel Environment Variables
- **Format**: `postgresql://user:password@host:5432/database`

### Error: "Could not create upload folder"
- **Cause**: Expected on Vercel (read-only filesystem)
- **Fix**: None needed — app continues normally with `/tmp/uploads`

### Error: "No module named 'psycopg2'"
- **Cause**: `psycopg2-binary` not installed
- **Fix**: Ensure `requirements.txt` includes `psycopg2-binary==2.9.9`
- **Redeploy**: `git push origin main` (if using GitHub integration)

### Static Files Not Loading
- **Cause**: Incorrect route configuration
- **Fix**: Verify `vercel.json` routes are correct
- **Check**: Browser developer tools → Network tab

### Slow Cold Starts
- **Cause**: Large dependencies (pandas, numpy)
- **Mitigation**: Consider upgrading to Vercel Pro for faster cold starts
- **Alternative**: Remove pandas/numpy if not critical (breaks dataset_processor)

## Rollback

If deployment fails, Vercel keeps previous working deployments:

1. Go to Vercel Dashboard → Your Project
2. Click **Deployments** tab
3. Find last working deployment
4. Click **⋯** → **Promote to Production**

## Environment Variables Reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | **Yes** (Vercel) | `sqlite:///resume_analyzer.db` | PostgreSQL connection string |
| `SECRET_KEY` | **Yes** (Production) | `dev-secret-key-...` | Flask session encryption key |
| `FLASK_ENV` | No | `production` | Flask environment mode |
| `UPLOAD_FOLDER` | No | Auto-detected | Upload directory path |
| `REQUIRED_SKILL_WEIGHT` | No | `1.0` | Weight for required skills |
| `OPTIONAL_SKILL_WEIGHT` | No | `0.5` | Weight for optional skills |
| `SKILLS_DATA_PATH` | No | `data/skills.json` | Skills database path |
| `JOB_ROLES_DATA_PATH` | No | `data/job_roles.json` | Job roles database path |
| `OPENAI_API_KEY` | No | None | OpenAI API key (optional AI features) |

## Security Notes

1. **Never commit `.env`**: Already in `.gitignore`
2. **Generate strong SECRET_KEY**: Use `python -c "import secrets; print(secrets.token_hex(32))"`
3. **Rotate keys regularly**: Update `SECRET_KEY` and database passwords periodically
4. **Database credentials**: Use Vercel's encrypted environment variables

## Next Steps After Deployment

1. **Custom Domain**: Add your domain in Vercel Project Settings → Domains
2. **Analytics**: Enable Vercel Analytics for traffic insights
3. **Monitoring**: Set up Sentry or similar for error tracking
4. **Performance**: Monitor Vercel logs for slow queries
5. **Scaling**: Upgrade plan if you exceed free tier limits

## Support & Resources

- **Vercel Documentation**: https://vercel.com/docs
- **Vercel Postgres Guide**: https://vercel.com/docs/storage/vercel-postgres
- **Project Repository**: https://github.com/Sapan02206/CareerPilot-AI
- **Flask on Vercel**: https://vercel.com/docs/frameworks/flask

---

**Last Updated**: October 11, 2026<br>
**Project Version**: 3.0.0<br>
**Deployment Platform**: Vercel (Serverless)
