"""
AI Resume Analyzer - Industry Grade v3.0
Flask application with:
  - Phase 1: Resume analysis against 25 job roles
  - Phase 2: Career readiness dashboard with progress tracking
  - Phase 3 (NEW): Custom JD matching + ATS compatibility scoring
"""

import os
import sys
import uuid
import threading
from datetime import datetime
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from werkzeug.utils import secure_filename

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

from config import Config
from models import db, Resume, UserSession, ReadinessSnapshot, UserProject
from modules.parser import ResumeParser
from modules.skill_extractor import SkillExtractor
from modules.matcher import SkillMatcher
from modules.recommender import SkillRecommender
from modules.readiness_calculator import ReadinessCalculator
from modules.jd_matcher import JDMatcher
from modules.ats_scorer import ATSScorer

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = Flask(__name__)
app.config.from_object(Config)
app.secret_key = app.config['SECRET_KEY']

db.init_app(app)

# Create upload folder — handles serverless read-only filesystems
try:
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
except OSError as e:
    # On serverless platforms (Vercel), only /tmp is writable
    # Config already handles /tmp detection, so this catches edge cases
    print(f"⚠️  Warning: Could not create upload folder: {e}")
    # App will continue — individual upload operations will handle errors

# ---------------------------------------------------------------------------
# Database initialisation — gunicorn-safe + serverless-safe
# ---------------------------------------------------------------------------
# db.create_all() runs ONCE at import time inside an app context.
# This works correctly whether the app is started with:
#   - `python app.py`          (direct run)
#   - `gunicorn app:app`       (production WSGI server)
#   - `flask run`              (Flask dev server)
#   - `vercel dev / vercel`    (Vercel serverless)
#
# For production with schema migrations, replace this block with
# Flask-Migrate (flask db upgrade) and remove create_all() entirely.
# See PYTHONANYWHERE_FIX.md for migration guidance.
#
# SQLAlchemy's create_all() is idempotent — it only creates tables that
# do not already exist, so calling it on startup is safe and cheap.
#
# On Vercel, DATABASE_URL MUST be configured to Vercel Postgres.
# Without DATABASE_URL, this will fail with SQLite on read-only filesystem.
try:
    with app.app_context():
        db.create_all()
    print("✅ Database tables initialized successfully")
except Exception as e:
    # Log the error but don't crash — allows health checks to pass
    # Database-dependent routes will fail with 500 errors
    print(f"❌ Database initialization failed: {e}")
    print("⚠️  App will start but database features will not work.")
    print("   → Set DATABASE_URL environment variable for PostgreSQL")
    print("   → Or ensure SQLite path is writable (local dev only)")
# ---------------------------------------------------------------------------
# Module initialisation (singletons — loaded once at startup)
# ---------------------------------------------------------------------------

skill_extractor = SkillExtractor(app.config['SKILLS_DATA_PATH'])
skill_matcher = SkillMatcher(
    app.config['JOB_ROLES_DATA_PATH'],
    app.config['REQUIRED_SKILL_WEIGHT'],
    app.config['OPTIONAL_SKILL_WEIGHT'],
)
skill_recommender = SkillRecommender()
readiness_calculator = ReadinessCalculator()
jd_matcher = JDMatcher(app.config['SKILLS_DATA_PATH'])
ats_scorer = ATSScorer()

# Optional: Kaggle dataset for demo mode (lazy-loaded on demand to optimize serverless cold starts)
_dataset_processor = None
_dataset_lock = threading.Lock()

def get_dataset_processor():
    """Thread-safe lazy loader for the Kaggle dataset processor.
    Defers loading the 17 MB CSV until demo routes are explicitly called.
    Caches the loaded instance for subsequent requests.
    """
    global _dataset_processor
    if _dataset_processor is not None:
        return _dataset_processor

    with _dataset_lock:
        if _dataset_processor is None:
            try:
                from modules.dataset_processor import DatasetProcessor
                processor = DatasetProcessor()
                processor.load_datasets()
                _dataset_processor = processor
                print("✅ Kaggle datasets loaded successfully (lazy loaded)!")
            except Exception as e:
                _dataset_processor = None
                print(f"⚠️  Kaggle datasets not loaded: {e}")
    return _dataset_processor

# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def allowed_file(filename: str) -> bool:
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']


def get_or_create_session() -> UserSession:
    """Return the UserSession DB record for the current browser session."""
    if 'session_id' not in session:
        session['session_id'] = str(uuid.uuid4())
    session_id = session['session_id']

    user_session = UserSession.query.filter_by(session_id=session_id).first()
    if not user_session:
        user_session = UserSession(session_id=session_id)
        db.session.add(user_session)
    else:
        user_session.last_active = datetime.utcnow()
    db.session.commit()
    return user_session


# ---------------------------------------------------------------------------
# Page routes
# ---------------------------------------------------------------------------

@app.route('/')
def index():
    """Main upload page."""
    roles_by_category = skill_matcher.get_roles_by_category()
    all_roles = skill_matcher.get_available_roles()
    return render_template('index.html', job_roles=all_roles,
                           roles_by_category=roles_by_category)


@app.route('/career-dashboard')
def career_dashboard():
    """Career readiness dashboard page."""
    return render_template('career_dashboard.html')


@app.route('/history')
def history():
    """Analysis history page."""
    try:
        resumes = Resume.query.order_by(Resume.created_at.desc()).limit(50).all()
        return render_template('history.html', resumes=resumes)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/demo')
def demo():
    """Demo mode with Kaggle dataset."""
    dp = get_dataset_processor()
    if dp is None:
        return render_template('index.html',
                               job_roles=skill_matcher.get_available_roles(),
                               roles_by_category=skill_matcher.get_roles_by_category(),
                               error="Demo dataset not available.")
    job_roles = skill_matcher.get_available_roles()
    kaggle_positions = dp.get_all_job_positions()[:10]
    return render_template('demo.html',
                           job_roles=job_roles,
                           kaggle_positions=kaggle_positions,
                           total_resumes=len(dp.resume_df))


# ---------------------------------------------------------------------------
# Core analysis routes
# ---------------------------------------------------------------------------

@app.route('/analyze', methods=['POST'])
def analyze():
    """
    Upload resume + select role → extract text → store in session → redirect to dashboard.
    Accepts both multipart/form-data (file upload) and optional jd_text field.
    """
    try:
        if 'resume' not in request.files:
            return jsonify({'error': 'No file uploaded'}), 400

        file = request.files['resume']
        job_role = request.form.get('job_role', '').strip()
        jd_text = request.form.get('jd_text', '').strip()   # optional custom JD

        if not file.filename:
            return jsonify({'error': 'No file selected'}), 400
        if not job_role:
            return jsonify({'error': 'No job role selected'}), 400
        if not allowed_file(file.filename):
            return jsonify({'error': 'Invalid file format. Only PDF and DOCX allowed'}), 400

        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)

        raw_text = ResumeParser.extract_text(file_path)
        os.remove(file_path)

        if not raw_text:
            return jsonify({'error': 'Failed to extract text from resume'}), 400

        cleaned_text = ResumeParser.clean_text(raw_text)

        # Get or create DB session
        user_session = get_or_create_session()
        user_session.target_role = job_role

        # Minimal session metadata (NO raw resume text)
        session['target_role'] = job_role
        session['filename'] = filename
        if jd_text:
            session['jd_text'] = jd_text
        session.pop('resume_text', None)

        # Run pipeline in memory immediately while file content is available
        enriched_skills = skill_extractor.extract_skills_with_experience(cleaned_text)
        basic_skills = [s['skill'] for s in enriched_skills]
        match_results = skill_matcher.match_skills(basic_skills, job_role)

        projects = UserProject.query.filter_by(session_id=user_session.session_id).all()
        readiness_data = readiness_calculator.calculate_readiness(
            enriched_skills, match_results, [p.to_dict() for p in projects]
        )

        required_keywords = match_results.get('matched_required', []) + \
                            match_results.get('missing_required', [])
        ats_result = ats_scorer.score(cleaned_text, required_keywords, job_role)

        # Persist snapshot with full breakdown & ATS score into database
        _save_snapshot(user_session.session_id, job_role, readiness_data,
                       enriched_skills, match_results, ats_score=ats_result)

        db.session.commit()

        return redirect(url_for('career_dashboard'))

    except Exception as e:
        return jsonify({'error': f'Analysis failed: {str(e)}'}), 500


@app.route('/compare-all', methods=['POST'])
def compare_all_roles():
    """Compare uploaded resume against all 25 roles."""
    try:
        if 'resume' not in request.files:
            return jsonify({'error': 'No file uploaded'}), 400
        file = request.files['resume']
        if not file.filename or not allowed_file(file.filename):
            return jsonify({'error': 'Invalid file'}), 400

        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)

        raw_text = ResumeParser.extract_text(file_path)
        os.remove(file_path)

        cleaned_text = ResumeParser.clean_text(raw_text)
        extracted_skills = skill_extractor.extract_skills(cleaned_text)
        all_matches = skill_matcher.compare_multiple_roles(extracted_skills)

        return jsonify({'extracted_skills': extracted_skills, 'role_matches': all_matches})

    except Exception as e:
        return jsonify({'error': f'Comparison failed: {str(e)}'}), 500


# ---------------------------------------------------------------------------
# Phase 2 — Career Readiness Dashboard API
# ---------------------------------------------------------------------------

@app.route('/dashboard', methods=['GET'])
def dashboard():
    """
    Career readiness dashboard data endpoint.
    Called by dashboard.js on page load via fetch('/dashboard').
    """
    try:
        user_session = get_or_create_session()
        target_role = session.get('target_role') or user_session.target_role

        if not target_role:
            return jsonify({'error': 'No target role set. Please upload a resume first.',
                            'redirect': '/'}), 400

        latest = ReadinessSnapshot.query.filter_by(
            session_id=user_session.session_id
        ).order_by(ReadinessSnapshot.created_at.desc()).first()

        # Check if legacy caller or test provided resume_text directly in session
        resume_text = session.pop('resume_text', None)
        if resume_text and (not latest or not latest.snapshot_data):
            enriched_skills = skill_extractor.extract_skills_with_experience(resume_text)
            basic_skills = [s['skill'] for s in enriched_skills]
            match_results = skill_matcher.match_skills(basic_skills, target_role)

            projects = UserProject.query.filter_by(session_id=user_session.session_id).all()
            readiness_data = readiness_calculator.calculate_readiness(
                enriched_skills, match_results, [p.to_dict() for p in projects]
            )
            required_keywords = match_results.get('matched_required', []) + \
                                match_results.get('missing_required', [])
            ats_result = ats_scorer.score(resume_text, required_keywords, target_role)

            _save_snapshot(user_session.session_id, target_role, readiness_data,
                           enriched_skills, match_results, ats_score=ats_result)

            return _dashboard_response(readiness_data, target_role,
                                       user_session.session_id, cached=False, ats_score=ats_result)

        if not latest or not latest.snapshot_data:
            return jsonify({'error': 'No resume data found. Please upload a resume first.',
                            'redirect': '/'}), 400

        enriched_skills = latest.snapshot_data.get('enriched_skills', [])
        match_results = latest.snapshot_data.get('match_results', {})

        if not enriched_skills or not match_results:
            return jsonify({'error': 'Cached data incomplete. Please re-upload your resume.',
                            'redirect': '/'}), 400

        projects = UserProject.query.filter_by(session_id=user_session.session_id).all()
        readiness_data = readiness_calculator.calculate_readiness(
            enriched_skills, match_results, [p.to_dict() for p in projects]
        )

        ats_score = latest.snapshot_data.get('ats_score')

        # Save a new snapshot only when any readiness component has changed
        # since the last snapshot. Compares all four scored dimensions so
        # that a project addition (evidence only) or a role change (skill
        # match only) is recorded even when the rounded overall score is
        # unchanged. Identical page-refresh reloads produce no duplicate row.
        if _readiness_changed(readiness_data, latest):
            _save_snapshot(user_session.session_id, target_role, readiness_data,
                           enriched_skills, match_results, ats_score=ats_score)

        return _dashboard_response(readiness_data, target_role,
                                   user_session.session_id, cached=True, ats_score=ats_score)

    except Exception as e:
        return jsonify({'error': f'Dashboard failed: {str(e)}'}), 500


def _readiness_changed(new_data: dict, latest_snapshot) -> bool:
    """
    Return True when any of the four readiness components differs meaningfully
    from the stored snapshot values, using a tolerance of 0.01 to avoid saving
    on pure floating-point noise.

    Compares: overall_score, skill_match_score, experience_score, evidence_score.

    Handles the case where latest_snapshot is None (first-time user) by
    returning True so the first snapshot is always saved.
    """
    if latest_snapshot is None:
        return True
    tolerance = 0.01
    components = [
        ('overall_score',     getattr(latest_snapshot, 'overall_score',     None)),
        ('skill_match_score', getattr(latest_snapshot, 'skill_match_score', None)),
        ('experience_score',  getattr(latest_snapshot, 'experience_score',  None)),
        ('evidence_score',    getattr(latest_snapshot, 'evidence_score',    None)),
    ]
    for key, stored_value in components:
        if stored_value is None:
            return True   # stored field missing — treat as changed
        new_value = new_data.get(key)
        if new_value is None:
            continue
        if abs(new_value - stored_value) > tolerance:
            return True
    return False


def _save_snapshot(session_id, target_role, readiness_data, enriched_skills, match_results, ats_score=None):
    """Persist a ReadinessSnapshot to the database."""
    snap_data = {
        'breakdown': readiness_data['breakdown'],
        'gap_analysis': readiness_data['gap_analysis'],
        'recommendations': readiness_data['recommendations'],
        'enriched_skills': enriched_skills,
        'match_results': match_results,
    }
    if ats_score is not None:
        snap_data['ats_score'] = ats_score

    snap = ReadinessSnapshot(
        session_id=session_id,
        target_role=target_role,
        overall_score=readiness_data['overall_score'],
        skill_match_score=readiness_data['skill_match_score'],
        experience_score=readiness_data['experience_score'],
        evidence_score=readiness_data['evidence_score'],
        snapshot_data=snap_data,
    )
    db.session.add(snap)
    db.session.commit()
    return snap


def _dashboard_response(readiness_data, target_role, session_id, cached=False, ats_score=None):
    """Build the standard dashboard JSON response."""
    resp = {
        'readiness': {
            'overall_score': readiness_data['overall_score'],
            'skill_match_score': readiness_data['skill_match_score'],
            'experience_score': readiness_data['experience_score'],
            'evidence_score': readiness_data['evidence_score'],
            'breakdown': readiness_data['breakdown'],
        },
        'gap_analysis': readiness_data['gap_analysis'],
        'recommendations': readiness_data['recommendations'],
        'target_role': target_role,
        'session_id': session_id,
        'cached': cached,
    }
    if ats_score is not None:
        resp['ats_score'] = ats_score
    return jsonify(resp)


@app.route('/set-target-role', methods=['POST'])
def set_target_role():
    """Update target role for current session."""
    try:
        data = request.get_json(silent=True) or {}
        target_role = data.get('target_role', '').strip()
        if not target_role:
            return jsonify({'error': 'target_role is required'}), 400

        available = skill_matcher.get_available_roles()
        if target_role not in available:
            return jsonify({'error': f'Unknown role. Available: {", ".join(available)}'}), 400

        user_session = get_or_create_session()
        user_session.target_role = target_role
        if data.get('email'):
            user_session.email = data['email']
        db.session.commit()

        return jsonify({'success': True, 'session_id': user_session.session_id,
                        'target_role': target_role})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/projects', methods=['GET', 'POST'])
def manage_projects():
    """GET list / POST add a portfolio project."""
    try:
        user_session = get_or_create_session()

        if request.method == 'GET':
            projects = UserProject.query.filter_by(
                session_id=user_session.session_id).all()
            return jsonify({'projects': [p.to_dict() for p in projects],
                            'total': len(projects)})

        data = request.get_json(silent=True) or {}
        if not data.get('title'):
            return jsonify({'error': 'title is required'}), 400

        def parse_date(s):
            return datetime.strptime(s, '%Y-%m-%d').date() if s else None

        project = UserProject(
            session_id=user_session.session_id,
            title=data['title'],
            description=data.get('description'),
            skills_used=data.get('skills_used', []),
            start_date=parse_date(data.get('start_date')),
            end_date=parse_date(data.get('end_date')),
            project_url=data.get('project_url'),
        )
        db.session.add(project)
        db.session.commit()
        return jsonify({'success': True, 'project': project.to_dict(),
                        'message': 'Project added successfully'}), 201

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/projects/<int:project_id>', methods=['DELETE'])
def delete_project(project_id):
    """Delete a project by ID."""
    try:
        user_session = get_or_create_session()
        project = UserProject.query.filter_by(
            id=project_id, session_id=user_session.session_id).first()
        if not project:
            return jsonify({'error': 'Project not found'}), 404
        db.session.delete(project)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Project deleted'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/progress', methods=['GET'])
def get_progress():
    """Return historical readiness score timeline."""
    try:
        user_session = get_or_create_session()
        snapshots = ReadinessSnapshot.query.filter_by(
            session_id=user_session.session_id
        ).order_by(ReadinessSnapshot.created_at.asc()).all()

        if not snapshots:
            return jsonify({'timeline': [], 'total_snapshots': 0,
                            'improvement': 0, 'target_role': user_session.target_role})

        timeline = [{
            'date': s.created_at.isoformat(),
            'overall_score': s.overall_score,
            'skill_match_score': s.skill_match_score,
            'experience_score': s.experience_score,
            'evidence_score': s.evidence_score,
        } for s in snapshots]

        improvement = snapshots[-1].overall_score - snapshots[0].overall_score
        return jsonify({
            'timeline': timeline,
            'total_snapshots': len(snapshots),
            'improvement': round(improvement, 2),
            'target_role': user_session.target_role or 'Not set',
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ---------------------------------------------------------------------------
# Phase 3 (NEW) — JD Matching & ATS Scoring APIs
# ---------------------------------------------------------------------------

@app.route('/api/match-jd', methods=['POST'])
def match_jd():
    """
    Match uploaded resume against a custom job description.

    Accepts multipart/form-data:
      - resume  (file, PDF/DOCX)  — OR —
      - resume_text (string, if already extracted)
      - jd_text (string, required) — raw job description text

    Returns:
      Full JD match result including score, keyword gaps, metadata,
      and ATS compatibility score for the JD keywords.
    """
    try:
        jd_text = (request.form.get('jd_text') or
                   (request.get_json(silent=True) or {}).get('jd_text', '')).strip()

        if not jd_text:
            return jsonify({'error': 'jd_text is required'}), 400

        # Get resume text: from upload, form field, or session
        resume_text = ''
        if 'resume' in request.files and request.files['resume'].filename:
            file = request.files['resume']
            if not allowed_file(file.filename):
                return jsonify({'error': 'Invalid file format. PDF/DOCX only'}), 400
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)
            raw = ResumeParser.extract_text(file_path)
            os.remove(file_path)
            resume_text = ResumeParser.clean_text(raw) if raw else ''
        elif request.form.get('resume_text'):
            resume_text = request.form.get('resume_text', '').strip()
        elif session.get('resume_text'):
            resume_text = session['resume_text']

        if not resume_text:
            return jsonify({'error': 'No resume provided. Upload a file or provide resume_text.'}), 400

        # Extract resume skills
        resume_skills = skill_extractor.extract_skills(resume_text)

        # JD match
        jd_result = jd_matcher.match(jd_text, resume_skills)

        # ATS score using JD required keywords as the target keyword list
        ats_keywords = jd_result['jd_skills']['required'] + jd_result['jd_skills']['preferred']
        ats_result = ats_scorer.score(resume_text, ats_keywords)

        return jsonify({
            'jd_match': jd_result,
            'ats_score': ats_result,
            'extracted_skills': resume_skills,
        })

    except Exception as e:
        return jsonify({'error': f'JD matching failed: {str(e)}'}), 500


@app.route('/api/ats-score', methods=['POST'])
def ats_score():
    """
    Run ATS compatibility check on a resume against optional keywords.

    Accepts multipart/form-data:
      - resume  (file, PDF/DOCX)  — OR —
      - resume_text (string)
      - keywords (comma-separated string, optional)
      - job_title (string, optional)

    Returns:
      Full ATS score report with grade, breakdown, and improvement tips.
    """
    try:
        resume_text = ''
        if 'resume' in request.files and request.files['resume'].filename:
            file = request.files['resume']
            if not allowed_file(file.filename):
                return jsonify({'error': 'Invalid file format'}), 400
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)
            raw = ResumeParser.extract_text(file_path)
            os.remove(file_path)
            resume_text = ResumeParser.clean_text(raw) if raw else ''
        elif request.form.get('resume_text'):
            resume_text = request.form.get('resume_text', '').strip()
        elif session.get('resume_text'):
            resume_text = session['resume_text']

        if not resume_text:
            return jsonify({'error': 'No resume provided'}), 400

        raw_keywords = request.form.get('keywords', '') or \
                       (request.get_json(silent=True) or {}).get('keywords', '')
        keywords = [k.strip() for k in raw_keywords.split(',') if k.strip()] \
                   if isinstance(raw_keywords, str) else raw_keywords

        job_title = request.form.get('job_title') or \
                    (request.get_json(silent=True) or {}).get('job_title')

        result = ats_scorer.score(resume_text, keywords, job_title)
        return jsonify(result)

    except Exception as e:
        return jsonify({'error': f'ATS scoring failed: {str(e)}'}), 500


@app.route('/api/top-roles', methods=['POST'])
def top_roles():
    """
    Return top 5 matching roles for a resume (no role pre-selection needed).

    Accepts multipart/form-data:
      - resume (file) — OR — resume_text (string in session)
    """
    try:
        resume_text = ''
        if 'resume' in request.files and request.files['resume'].filename:
            file = request.files['resume']
            if not allowed_file(file.filename):
                return jsonify({'error': 'Invalid file format'}), 400
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)
            raw = ResumeParser.extract_text(file_path)
            os.remove(file_path)
            resume_text = ResumeParser.clean_text(raw) if raw else ''
        elif session.get('resume_text'):
            resume_text = session['resume_text']

        if not resume_text:
            return jsonify({'error': 'No resume provided'}), 400

        resume_skills = skill_extractor.extract_skills(resume_text)
        top = skill_matcher.get_top_matches(resume_skills, top_n=5)
        return jsonify({'top_matches': top, 'extracted_skills': resume_skills})

    except Exception as e:
        return jsonify({'error': f'Role matching failed: {str(e)}'}), 500


# ---------------------------------------------------------------------------
# General API endpoints
# ---------------------------------------------------------------------------

@app.route('/api/roles', methods=['GET'])
def get_roles():
    """All available job roles, optionally grouped by category."""
    by_category = request.args.get('grouped', 'false').lower() == 'true'
    if by_category:
        return jsonify(skill_matcher.get_roles_by_category())
    return jsonify({'roles': skill_matcher.get_available_roles()})


@app.route('/api/role/<path:role_name>', methods=['GET'])
def get_role_details(role_name):
    """Details for a specific role."""
    details = skill_matcher.get_role_details(role_name)
    if details:
        return jsonify(details)
    return jsonify({'error': 'Role not found'}), 404


@app.route('/api/history', methods=['GET'])
def api_history():
    """Analysis history."""
    try:
        limit = request.args.get('limit', 50, type=int)
        resumes = Resume.query.order_by(Resume.created_at.desc()).limit(limit).all()
        return jsonify({'total': Resume.query.count(),
                        'resumes': [r.to_dict() for r in resumes]})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/stats', methods=['GET'])
def api_stats():
    """Aggregate usage statistics."""
    try:
        total = Resume.query.count()
        avg_score = db.session.query(db.func.avg(Resume.match_score)).scalar() or 0
        role_stats = db.session.query(
            Resume.job_role, db.func.count(Resume.id).label('count')
        ).group_by(Resume.job_role).order_by(db.text('count DESC')).limit(5).all()
        return jsonify({
            'total_analyses': total,
            'average_match_score': round(avg_score, 2),
            'top_job_roles': [{'role': r, 'count': c} for r, c in role_stats],
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/analyze-kaggle', methods=['POST'])
def analyze_kaggle():
    """Demo: analyze a Kaggle dataset resume."""
    try:
        dp = get_dataset_processor()
        if dp is None:
            return jsonify({'error': 'Kaggle datasets not loaded'}), 500
        job_role = request.form.get('job_role')
        position_filter = request.form.get('position_filter')
        if not job_role:
            return jsonify({'error': 'No job role selected'}), 400

        if position_filter and position_filter != 'random':
            sample = dp.get_resume_by_position(position_filter, 1)
            if len(sample) == 0:
                sample = dp.get_random_resume(1)
        else:
            sample = dp.get_random_resume(1)

        row = sample.iloc[0]
        extracted_skills = dp.extract_resume_skills(row)
        resume_text = dp.create_resume_text(row)
        categorized = skill_extractor.categorize_skills(extracted_skills)
        match_results = skill_matcher.match_skills(extracted_skills, job_role)
        recommendations = skill_recommender.generate_recommendations(match_results)

        return render_template('results.html', results={
            'resume_text': resume_text,
            'extracted_skills': extracted_skills,
            'categorized_skills': categorized,
            'match_results': match_results,
            'recommendations': recommendations,
            'source': 'Kaggle Dataset',
            'dataset_position': row.get('positions', 'N/A'),
        }, is_demo=True)
    except Exception as e:
        return jsonify({'error': f'Analysis failed: {str(e)}'}), 500


@app.route('/api/kaggle-stats', methods=['GET'])
def kaggle_stats():
    dp = get_dataset_processor()
    if dp is None:
        return jsonify({'error': 'Kaggle datasets not loaded'}), 500
    return jsonify(dp.get_dataset_statistics())


@app.route('/api/kaggle-positions', methods=['GET'])
def kaggle_positions():
    dp = get_dataset_processor()
    if dp is None:
        return jsonify({'error': 'Kaggle datasets not loaded'}), 500
    positions = dp.get_all_job_positions()
    return jsonify({'positions': positions, 'total': len(positions)})


def __getattr__(name):
    """Module-level attribute fallback for backward compatibility."""
    if name == 'dataset_processor':
        return get_dataset_processor()
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


# ---------------------------------------------------------------------------
# Error handlers
# ---------------------------------------------------------------------------

@app.errorhandler(404)
def not_found(e):
    return jsonify({'error': 'Endpoint not found', 'code': 404}), 404


@app.errorhandler(413)
def file_too_large(e):
    return jsonify({'error': 'File too large. Maximum size is 16MB', 'code': 413}), 413


@app.errorhandler(500)
def server_error(e):
    return jsonify({'error': 'Internal server error', 'code': 500}), 500


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
