"""
Application Configuration - Industry Upgrade v3.0
All settings loaded from environment variables with safe defaults.
"""

import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # ------------------------------------------------------------------ #
    #  Flask core                                                          #
    # ------------------------------------------------------------------ #
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-CHANGE-IN-PRODUCTION'
    MAX_CONTENT_LENGTH = 3.5 * 1024 * 1024   # 3.5 MB - Vercel free tier compatible with multipart overhead margin

    # ------------------------------------------------------------------ #
    #  File uploads                                                        #
    # ------------------------------------------------------------------ #
    # Detect serverless environments (Vercel, AWS Lambda) and use /tmp
    _default_upload = '/tmp/uploads' if os.environ.get('VERCEL') or os.environ.get('AWS_LAMBDA_FUNCTION_NAME') else 'uploads'
    UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', _default_upload)
    ALLOWED_EXTENSIONS = {'pdf', 'docx'}

    # ------------------------------------------------------------------ #
    #  Database                                                            #
    # ------------------------------------------------------------------ #
    # Priority: DATABASE_URL env var (PostgreSQL/MySQL) → SQLite fallback
    # SQLite uses instance/ subdirectory for data persistence
    _db_url = os.environ.get('DATABASE_URL', '')

    # Fix for older Heroku/Railway postgres:// URL scheme
    if _db_url.startswith('postgres://'):
        _db_url = _db_url.replace('postgres://', 'postgresql://', 1)

    # SQLite path: use absolute path to instance/resume_analyzer.db
    # This ensures consistent behavior across platforms (local dev, PythonAnywhere, etc.)
    if not _db_url:
        _basedir = os.path.abspath(os.path.dirname(__file__))
        _db_file = os.path.join(_basedir, 'instance', 'resume_analyzer.db')
        SQLALCHEMY_DATABASE_URI = f'sqlite:///{_db_file}'
    else:
        SQLALCHEMY_DATABASE_URI = _db_url
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,       # reconnect on stale connections
        'pool_recycle': 300,         # recycle connections every 5 min
    }

    # ------------------------------------------------------------------ #
    #  Skill matching weights                                              #
    # ------------------------------------------------------------------ #
    REQUIRED_SKILL_WEIGHT = float(os.environ.get('REQUIRED_SKILL_WEIGHT', 1.0))
    OPTIONAL_SKILL_WEIGHT = float(os.environ.get('OPTIONAL_SKILL_WEIGHT', 0.5))

    # ------------------------------------------------------------------ #
    #  Data file paths                                                     #
    # ------------------------------------------------------------------ #
    SKILLS_DATA_PATH = os.environ.get('SKILLS_DATA_PATH', 'data/skills.json')
    JOB_ROLES_DATA_PATH = os.environ.get('JOB_ROLES_DATA_PATH', 'data/job_roles.json')

    # ------------------------------------------------------------------ #
    #  Optional integrations                                               #
    # ------------------------------------------------------------------ #
    OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
    USE_OPENAI = bool(OPENAI_API_KEY)

    # ------------------------------------------------------------------ #
    #  Session configuration                                               #
    # ------------------------------------------------------------------ #
    SESSION_COOKIE_SECURE = os.environ.get('FLASK_ENV') == 'production'
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 24 * 30   # 30 days

    # ------------------------------------------------------------------ #
    #  App metadata                                                        #
    # ------------------------------------------------------------------ #
    APP_VERSION = '3.0.0'
    APP_NAME = 'AI Resume Analyzer'
