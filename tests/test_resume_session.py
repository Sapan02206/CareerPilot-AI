"""
Tests for Hardened Resume Session Storage & Serverless Robustness.

Covers:
1. Resumes of 10 KB, 50 KB, and 100 KB:
   - Upload succeeds without cookie overflow
   - Set-Cookie header remains tiny (< 500 bytes, well below 4096-byte limit)
   - Zero raw resume text is stored in client cookies
2. Complete upload-to-dashboard workflow
3. Dashboard refresh behavior (ATS score persistence and duplicate snapshot suppression)
4. Project evidence recalculation on project addition
5. Session isolation between concurrent users
6. Missing / expired session state handling
"""

import io
import os
import sys
import tempfile
import docx
import pytest
from sqlalchemy import create_engine

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app import app, db
from models import UserSession, ReadinessSnapshot, UserProject


# ---------------------------------------------------------------------------
# Test Fixtures (Completely Isolated Temporary SQLite - zero writes to instance DB)
# ---------------------------------------------------------------------------

@pytest.fixture
def test_client():
    """Create Flask test client with an isolated temporary SQLite database."""
    temp_db_fd, temp_db_path = tempfile.mkstemp(suffix=".db")
    os.close(temp_db_fd)

    test_engine = create_engine(f"sqlite:///{temp_db_path}")
    orig_testing = app.config.get('TESTING', False)
    app.config['TESTING'] = True

    with app.app_context():
        sa = app.extensions['sqlalchemy']
        orig_engine = sa.engines.get(None)
        sa.engines[None] = test_engine

        db.metadata.create_all(bind=test_engine)

        try:
            with app.test_client() as client:
                yield client
        finally:
            db.session.remove()
            test_engine.dispose()
            sa.engines[None] = orig_engine
            app.config['TESTING'] = orig_testing
            if os.path.exists(temp_db_path):
                try:
                    os.remove(temp_db_path)
                except OSError:
                    pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_docx_file(text: str) -> io.BytesIO:
    """Generate an in-memory .docx file with paragraphs from text."""
    doc = docx.Document()
    for paragraph in text.split("\n"):
        if paragraph.strip():
            doc.add_paragraph(paragraph)
    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf


def _generate_realistic_resume(target_size_kb: int) -> str:
    """
    Generate realistic resume text that reaches at least target_size_kb KB.
    Contains valid contact info, technical skills, and quantified action verbs.
    """
    header = (
        "John Doe\n"
        "Email: john.doe@example.com | Phone: +1-555-0199\n"
        "LinkedIn: https://linkedin.com/in/johndoe | GitHub: https://github.com/johndoe\n\n"
        "PROFESSIONAL SUMMARY\n"
        "Senior Frontend Developer with expertise in building responsive web applications.\n"
        "Skilled in HTML, CSS, JavaScript, React, Git, Responsive Design, and REST APIs.\n\n"
        "CORE TECHNICAL SKILLS\n"
        "JavaScript, React, HTML5, CSS3, Git, Responsive Design, REST APIs, TypeScript, Webpack, Redux\n\n"
        "PROFESSIONAL EXPERIENCE\n"
    )

    experience_block = (
        "Senior Software Engineer | Tech Corp (2021 - Present)\n"
        "- Developed responsive web design solutions improving customer retention by 28%.\n"
        "- Built 15+ single page applications using React, HTML, CSS, and modern JavaScript.\n"
        "- Implemented REST APIs and optimized load times by 40% across 50,000 daily active users.\n"
        "- Managed version control workflows using Git and led a cross-functional team of 6 engineers.\n"
        "- Architected reusable UI component libraries saving 120 development hours per sprint.\n\n"
        "Frontend Engineer | Web Solutions Inc (2018 - 2021)\n"
        "- Engineered interactive web portals using JavaScript and responsive design principles.\n"
        "- Collaborated with UI/UX designers to deliver accessible interfaces for 200,000 users.\n"
        "- Integrated RESTful endpoints and reduced API latency by 35% using caching strategies.\n"
        "- Automated frontend testing pipelines achieving 94% test coverage.\n\n"
    )

    text = header
    while len(text.encode('utf-8')) < (target_size_kb * 1024):
        text += experience_block

    return text


# ---------------------------------------------------------------------------
# Test Cases
# ---------------------------------------------------------------------------

class TestResumeSessionHardening:

    @pytest.mark.parametrize("size_kb", [10, 50, 100])
    def test_large_resume_uploads_without_cookie_overflow(self, test_client, size_kb):
        """
        Verify that uploading resumes of 10 KB, 50 KB, and 100 KB succeeds and
        NEVER stores raw resume text in client-side cookies or exceeds cookie limits.
        """
        resume_text = _generate_realistic_resume(size_kb)
        docx_bytes = _create_docx_file(resume_text)

        # Upload resume
        resp = test_client.post('/analyze', data={
            'resume': (docx_bytes, f'resume_{size_kb}kb.docx'),
            'job_role': 'Frontend Developer'
        }, content_type='multipart/form-data')

        # 1. Verify successful redirect
        assert resp.status_code == 302, f"Expected 302 redirect, got {resp.status_code}"
        assert '/career-dashboard' in resp.headers.get('Location', '')

        # 2. Check Set-Cookie headers
        cookie_headers = resp.headers.getlist('Set-Cookie')
        for cookie_str in cookie_headers:
            # Cookie size must be small (< 500 bytes) and well below the 4096-byte limit
            assert len(cookie_str) < 500, (
                f"Cookie size ({len(cookie_str)} bytes) is too large for {size_kb} KB resume! "
                "Raw resume text is likely being stored in the cookie."
            )
            # Cookie must NOT contain resume words or PII
            assert "PROFESSIONAL SUMMARY" not in cookie_str
            assert "john.doe@example.com" not in cookie_str

        # 3. Access dashboard and verify data is retrieved cleanly
        dash_resp = test_client.get('/dashboard')
        assert dash_resp.status_code == 200, f"Dashboard returned {dash_resp.status_code}"
        data = dash_resp.get_json()

        assert data['target_role'] == 'Frontend Developer'
        assert data['readiness']['overall_score'] > 0
        assert data['ats_score'] is not None
        assert data['ats_score']['total_score'] > 0

    def test_complete_upload_to_dashboard_workflow(self, test_client):
        """
        Test the complete workflow:
        Upload resume -> redirect -> load dashboard -> check full readiness & ATS results.
        """
        resume_text = _generate_realistic_resume(10)
        docx_bytes = _create_docx_file(resume_text)

        # Step 1: Upload
        upload_resp = test_client.post('/analyze', data={
            'resume': (docx_bytes, 'frontend_resume.docx'),
            'job_role': 'Frontend Developer'
        }, content_type='multipart/form-data')
        assert upload_resp.status_code == 302

        # Step 2: GET /career-dashboard page
        page_resp = test_client.get('/career-dashboard')
        assert page_resp.status_code == 200
        assert b"career-dashboard" in page_resp.data or b"Dashboard" in page_resp.data

        # Step 3: GET /dashboard API (called by dashboard.js)
        dash_resp = test_client.get('/dashboard')
        assert dash_resp.status_code == 200
        data = dash_resp.get_json()

        # Verify readiness breakdown
        readiness = data['readiness']
        assert 'overall_score' in readiness
        assert 'skill_match_score' in readiness
        assert 'experience_score' in readiness
        assert 'evidence_score' in readiness
        assert 'breakdown' in readiness

        # Verify ATS scoring
        ats = data['ats_score']
        assert ats is not None
        assert 'total_score' in ats
        assert 'breakdown' in ats

        # Verify gap analysis
        gap = data['gap_analysis']
        assert 'matched_required' in gap
        assert 'missing_required' in gap

    def test_dashboard_refresh_preserves_ats_score_and_prevents_duplicates(self, test_client):
        """
        Verify that refreshing the dashboard:
        1. Keeps the ATS score intact on every refresh
        2. Does NOT create duplicate snapshot rows when scores have not changed
        """
        resume_text = _generate_realistic_resume(10)
        docx_bytes = _create_docx_file(resume_text)

        # Upload
        test_client.post('/analyze', data={
            'resume': (docx_bytes, 'refresh_test.docx'),
            'job_role': 'Frontend Developer'
        }, content_type='multipart/form-data')

        # Snapshot count after upload must be exactly 1
        with app.app_context():
            assert ReadinessSnapshot.query.count() == 1

        # First dashboard visit
        res1 = test_client.get('/dashboard').get_json()
        assert res1['ats_score'] is not None

        # Refresh 1
        res2 = test_client.get('/dashboard').get_json()
        assert res2['ats_score'] is not None
        assert res2['ats_score']['total_score'] == res1['ats_score']['total_score']

        # Refresh 2
        res3 = test_client.get('/dashboard').get_json()
        assert res3['ats_score'] is not None

        # Verify snapshot count remains exactly 1 (duplicate suppression)
        with app.app_context():
            assert ReadinessSnapshot.query.count() == 1

    def test_project_evidence_recalculation_and_progress_tracking(self, test_client):
        """
        Verify that adding a project:
        1. Recalculates evidence score dynamically on next dashboard load
        2. Saves a new snapshot because evidence changed
        3. Preserves the ATS score in the updated snapshot
        4. Accurately updates the /api/progress timeline
        """
        resume_text = _generate_realistic_resume(10)
        docx_bytes = _create_docx_file(resume_text)

        test_client.post('/analyze', data={
            'resume': (docx_bytes, 'project_test.docx'),
            'job_role': 'Frontend Developer'
        }, content_type='multipart/form-data')

        initial_dash = test_client.get('/dashboard').get_json()
        initial_evidence = initial_dash['readiness']['evidence_score']
        initial_ats = initial_dash['ats_score']
        assert initial_evidence == 0.0

        # Add a user project matching a Frontend skill
        proj_resp = test_client.post('/api/projects', json={
            'title': 'E-Commerce React Store',
            'description': 'Built responsive web store with React and JavaScript',
            'skills_used': ['React', 'JavaScript', 'HTML'],
            'project_url': 'https://github.com/example/react-store'
        })
        assert proj_resp.status_code == 201

        # Load dashboard again — should trigger evidence score increase
        updated_dash = test_client.get('/dashboard').get_json()
        updated_evidence = updated_dash['readiness']['evidence_score']
        assert updated_evidence > initial_evidence
        # ATS score must still be present
        assert updated_dash['ats_score'] is not None
        assert updated_dash['ats_score']['total_score'] == initial_ats['total_score']

        # Verify a second snapshot was created because evidence changed
        with app.app_context():
            assert ReadinessSnapshot.query.count() == 2

        # Check progress timeline
        prog_resp = test_client.get('/api/progress')
        assert prog_resp.status_code == 200
        prog_data = prog_resp.get_json()
        assert prog_data['total_snapshots'] == 2
        assert len(prog_data['timeline']) == 2
        assert prog_data['improvement'] >= 0

    def test_session_isolation_between_different_users(self, test_client):
        """
        Verify complete session isolation:
        User A's uploaded resume and data cannot be seen or accessed by User B.
        """
        # User A uploads a resume
        resume_a = _generate_realistic_resume(10)
        test_client.post('/analyze', data={
            'resume': (_create_docx_file(resume_a), 'user_a.docx'),
            'job_role': 'Frontend Developer'
        }, content_type='multipart/form-data')

        dash_a = test_client.get('/dashboard').get_json()
        assert dash_a['target_role'] == 'Frontend Developer'

        # User B uses a separate client session (fresh cookies)
        with app.test_client() as client_b:
            # User B visits dashboard before uploading anything -> must be redirected
            dash_b_initial = client_b.get('/dashboard')
            assert dash_b_initial.status_code == 400
            assert dash_b_initial.get_json().get('redirect') == '/'

            # User B uploads a different role
            client_b.post('/analyze', data={
                'resume': (_create_docx_file(resume_a), 'user_b.docx'),
                'job_role': 'Data Scientist'
            }, content_type='multipart/form-data')

            dash_b = client_b.get('/dashboard').get_json()
            assert dash_b['target_role'] == 'Data Scientist'

        # User A visits dashboard again -> must STILL be Frontend Developer
        dash_a_again = test_client.get('/dashboard').get_json()
        assert dash_a_again['target_role'] == 'Frontend Developer'

    def test_missing_or_expired_session_returns_graceful_redirect(self, test_client):
        """
        Verify that visiting /dashboard with no uploaded resume or expired session
        returns an HTTP 400 response with redirect: '/'.
        """
        resp = test_client.get('/dashboard')
        assert resp.status_code == 400
        data = resp.get_json()
        assert 'error' in data
        assert data.get('redirect') == '/'
