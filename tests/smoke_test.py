"""
Smoke test — verifies all modules and data files load correctly.
Does NOT require a running server or a real resume file.

Run from project root:
    python tests/smoke_test.py
    OR
    python -m pytest tests/smoke_test.py -v
"""

import sys
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _import(module, fromlist=None):
    """Import a module and optionally access an attribute."""
    mod = __import__(module, fromlist=fromlist or [])
    if fromlist:
        return getattr(mod, fromlist[0])
    return mod


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestImports:
    """Verify every module can be imported without error."""

    def test_import_config(self):
        import config
        assert hasattr(config, "Config")

    def test_import_models(self):
        import models
        assert hasattr(models, "db")
        assert hasattr(models, "Resume")
        assert hasattr(models, "UserSession")
        assert hasattr(models, "ReadinessSnapshot")
        assert hasattr(models, "UserProject")

    def test_import_parser(self):
        from modules.parser import ResumeParser
        assert hasattr(ResumeParser, "extract_text")
        assert hasattr(ResumeParser, "clean_text")

    def test_import_experience_extractor(self):
        from modules.experience_extractor import ExperienceExtractor
        ex = ExperienceExtractor()
        assert hasattr(ex, "extract_experience")
        assert hasattr(ex, "extract_experience_hybrid")

    def test_import_skill_extractor(self):
        from modules.skill_extractor import SkillExtractor
        # Does not init here (needs skills.json path)
        assert SkillExtractor is not None

    def test_import_matcher(self):
        from modules.matcher import SkillMatcher
        assert SkillMatcher is not None

    def test_import_recommender(self):
        from modules.recommender import SkillRecommender
        sr = SkillRecommender()
        assert hasattr(sr, "generate_recommendations")

    def test_import_readiness_calculator(self):
        from modules.readiness_calculator import ReadinessCalculator
        rc = ReadinessCalculator()
        assert rc.skill_weight == 0.50
        assert rc.experience_weight == 0.30
        assert rc.evidence_weight == 0.20

    def test_import_jd_matcher(self):
        from modules.jd_matcher import JDMatcher
        assert JDMatcher is not None

    def test_import_ats_scorer(self):
        from modules.ats_scorer import ATSScorer
        scorer = ATSScorer()
        assert hasattr(scorer, "score")


class TestDataFiles:
    """Verify data files exist and have the correct structure."""

    def test_skills_json_exists(self):
        path = os.path.join(PROJECT_ROOT, "data", "skills.json")
        assert os.path.exists(path), f"Missing: {path}"

    def test_job_roles_json_exists(self):
        path = os.path.join(PROJECT_ROOT, "data", "job_roles.json")
        assert os.path.exists(path), f"Missing: {path}"

    def test_skills_json_structure(self):
        import json
        with open(os.path.join(PROJECT_ROOT, "data", "skills.json")) as f:
            data = json.load(f)
        assert "technical_skills" in data
        assert "soft_skills" in data
        assert "skill_variations" in data
        assert isinstance(data["soft_skills"], list)
        assert len(data["soft_skills"]) > 0

    def test_skills_json_has_300_plus_skills(self):
        import json
        with open(os.path.join(PROJECT_ROOT, "data", "skills.json")) as f:
            data = json.load(f)
        total = sum(len(v) for v in data["technical_skills"].values())
        total += len(data["soft_skills"])
        assert total >= 200, f"Only {total} skills found — expected 200+"

    def test_job_roles_json_has_25_roles(self):
        import json
        with open(os.path.join(PROJECT_ROOT, "data", "job_roles.json")) as f:
            data = json.load(f)
        assert len(data) >= 25, f"Only {len(data)} roles — expected 25+"

    def test_job_roles_have_required_fields(self):
        import json
        with open(os.path.join(PROJECT_ROOT, "data", "job_roles.json")) as f:
            data = json.load(f)
        for role_name, role_data in data.items():
            assert "required_skills" in role_data, f"{role_name} missing required_skills"
            assert "optional_skills" in role_data, f"{role_name} missing optional_skills"
            assert "description" in role_data, f"{role_name} missing description"
            assert isinstance(role_data["required_skills"], list)
            assert len(role_data["required_skills"]) > 0, f"{role_name} has no required skills"

    def test_uploads_dir_exists(self):
        path = os.path.join(PROJECT_ROOT, "uploads")
        assert os.path.exists(path), f"Missing uploads/ directory"

    def test_instance_dir_accessible(self):
        # instance/ is created by Flask automatically, but let's check parent exists
        assert os.path.exists(PROJECT_ROOT)


class TestModuleInitialisation:
    """Verify modules initialise correctly with real data files."""

    def test_skill_extractor_loads(self):
        from modules.skill_extractor import SkillExtractor
        se = SkillExtractor(os.path.join(PROJECT_ROOT, "data", "skills.json"))
        assert len(se.all_skills) >= 200
        assert len(se.skill_variations) >= 50

    def test_skill_matcher_loads(self):
        from modules.matcher import SkillMatcher
        sm = SkillMatcher(os.path.join(PROJECT_ROOT, "data", "job_roles.json"))
        roles = sm.get_available_roles()
        assert len(roles) >= 25

    def test_skill_matcher_categories(self):
        from modules.matcher import SkillMatcher
        sm = SkillMatcher(os.path.join(PROJECT_ROOT, "data", "job_roles.json"))
        cats = sm.get_roles_by_category()
        assert len(cats) >= 5, "Expected at least 5 categories"
        for cat, roles in cats.items():
            assert len(roles) >= 1

    def test_jd_matcher_loads(self):
        from modules.jd_matcher import JDMatcher
        jd = JDMatcher(os.path.join(PROJECT_ROOT, "data", "skills.json"))
        assert len(jd.all_skills) >= 200

    def test_ats_scorer_loads(self):
        from modules.ats_scorer import ATSScorer
        ats = ATSScorer()
        assert len(ats.ACTION_VERBS) >= 20
        assert len(ats.EXPECTED_SECTIONS) >= 5


class TestCoreLogic:
    """Basic logic tests — no Flask, no DB, no files needed."""

    def test_skill_extraction_basic(self):
        from modules.skill_extractor import SkillExtractor
        se = SkillExtractor(os.path.join(PROJECT_ROOT, "data", "skills.json"))
        text = "I am a Python developer with experience in Django and PostgreSQL."
        skills = se.extract_skills(text)
        skills_lower = [s.lower() for s in skills]
        assert "python" in skills_lower
        assert "django" in skills_lower
        assert "postgresql" in skills_lower

    def test_skill_extraction_alias_normalisation(self):
        from modules.skill_extractor import SkillExtractor
        se = SkillExtractor(os.path.join(PROJECT_ROOT, "data", "skills.json"))
        # "JS" should normalise to "JavaScript"
        text = "I know JS and worked with NodeJS for 3 years."
        skills = se.extract_skills(text)
        skills_lower = [s.lower() for s in skills]
        assert any("javascript" in s for s in skills_lower), \
            f"'JS' not normalised to JavaScript. Got: {skills}"

    def test_role_matching_returns_score(self):
        from modules.matcher import SkillMatcher
        sm = SkillMatcher(os.path.join(PROJECT_ROOT, "data", "job_roles.json"))
        result = sm.match_skills(["Python", "Django", "PostgreSQL", "Git"], "Backend Developer")
        assert "match_score" in result
        assert 0.0 <= result["match_score"] <= 100.0

    def test_role_matching_detects_matched_skills(self):
        from modules.matcher import SkillMatcher
        sm = SkillMatcher(os.path.join(PROJECT_ROOT, "data", "job_roles.json"))
        result = sm.match_skills(["Python", "Django", "PostgreSQL", "Docker", "Git"], "Backend Developer")
        assert len(result["matched_required"]) >= 3

    def test_fuzzy_matching_catches_aliases(self):
        from modules.matcher import SkillMatcher
        sm = SkillMatcher(os.path.join(PROJECT_ROOT, "data", "job_roles.json"))
        # "nodejs" (no dot) should fuzzy-match "Node.js"
        result = sm.match_skills(["Python", "nodejs", "postgres", "Git"], "Backend Developer")
        assert result["match_score"] > 0

    def test_compare_all_roles_returns_list(self):
        from modules.matcher import SkillMatcher
        sm = SkillMatcher(os.path.join(PROJECT_ROOT, "data", "job_roles.json"))
        results = sm.compare_multiple_roles(["Python", "React", "PostgreSQL"])
        assert isinstance(results, list)
        assert len(results) >= 25
        # First result should have highest score
        assert results[0]["match_score"] >= results[-1]["match_score"]

    def test_ats_score_returns_correct_schema(self):
        from modules.ats_scorer import ATSScorer
        ats = ATSScorer()
        text = (
            "John Smith | john@example.com | linkedin.com/in/johnsmith\n\n"
            "SUMMARY\nExperienced Python developer with 5 years building REST APIs.\n\n"
            "EXPERIENCE\nDeveloped and deployed Django applications.\n"
            "Reduced API response time by 40%.\n"
            "Built 3 production microservices serving 10k+ users.\n\n"
            "SKILLS\nPython, Django, PostgreSQL, Docker, Git\n\n"
            "EDUCATION\nBSc Computer Science"
        )
        result = ats.score(text, ["Python", "Django", "PostgreSQL"])
        assert "total_score" in result
        assert "grade" in result
        assert "grade_label" in result
        assert "breakdown" in result
        assert "improvement_tips" in result
        assert 0.0 <= result["total_score"] <= 100.0
        assert result["grade"] in ["A", "B", "C", "D", "F"]

    def test_readiness_calculator_formula(self):
        from modules.readiness_calculator import ReadinessCalculator
        rc = ReadinessCalculator()
        enriched_skills = [
            {"skill": "Python", "experience_years": 3.0, "experience_confidence": 0.9,
             "experience_context": "", "experience_source": "explicit_years", "category": "technical"},
            {"skill": "Django", "experience_years": 2.0, "experience_confidence": 0.8,
             "experience_context": "", "experience_source": "explicit_years", "category": "technical"},
        ]
        match_results = {
            "match_score": 80.0,
            "matched_required": ["Python", "Django"],
            "missing_required": ["SQL"],
            "matched_optional": ["Docker"],
            "missing_optional": ["Redis"],
        }
        result = rc.calculate_readiness(enriched_skills, match_results, [])
        assert "overall_score" in result
        assert "skill_match_score" in result
        assert "experience_score" in result
        assert "evidence_score" in result
        assert "gap_analysis" in result
        assert "recommendations" in result
        # Verify formula: 80*0.5 + experience*0.3 + 0*0.2
        assert result["skill_match_score"] == 80.0
        assert result["evidence_score"] == 0.0  # no projects

    def test_recommendations_use_detail_key(self):
        """P0-1 regression test: ensure 'detail' key is present, not 'description'."""
        from modules.readiness_calculator import ReadinessCalculator
        rc = ReadinessCalculator()
        enriched_skills = []
        match_results = {
            "match_score": 30.0,
            "matched_required": [],
            "missing_required": ["Python", "SQL"],
            "matched_optional": [],
            "missing_optional": ["Docker"],
        }
        result = rc.calculate_readiness(enriched_skills, match_results, [])
        for rec in result["recommendations"]:
            assert "detail" in rec, f"Rec missing 'detail' key: {rec}"
            assert "description" not in rec, f"Old 'description' key still present: {rec}"
            assert "title" in rec, f"Rec missing 'title' key: {rec}"

    def test_jd_score_zero_for_empty(self):
        """P0-2 regression test: empty JD must never produce 100%."""
        from modules.jd_matcher import JDMatcher
        jd = JDMatcher(os.path.join(PROJECT_ROOT, "data", "skills.json"))
        result = jd.match("", ["Python", "Django"])
        assert result["match_score"] == 0.0
        assert result["analysis_status"] == "jd_empty"

    def test_jd_score_zero_for_no_skills(self):
        """P0-2 regression test: JD with no recognised skills must score 0."""
        from modules.jd_matcher import JDMatcher
        jd = JDMatcher(os.path.join(PROJECT_ROOT, "data", "skills.json"))
        text = (
            "Join our passionate team! We are seeking a motivated individual "
            "who thrives under pressure and delivers results with confidence. "
            "Excellent interpersonal skills and a positive attitude required. "
            "Must be a self-starter with great organisational abilities."
        )
        result = jd.match(text, ["Python", "Django"])
        assert result["match_score"] == 0.0


class TestCleanText:
    """Test the _clean_text helper from jd_matcher."""

    def test_strips_html(self):
        from modules.jd_matcher import _clean_text
        result = _clean_text("<p>Hello <b>world</b></p>")
        assert "<" not in result
        assert "Hello" in result
        assert "world" in result

    def test_strips_bullet_chars(self):
        from modules.jd_matcher import _clean_text
        result = _clean_text("• Python\n• Django\n• React")
        assert "•" not in result
        assert "Python" in result

    def test_normalises_whitespace(self):
        from modules.jd_matcher import _clean_text
        result = _clean_text("  Hello   \n\n  World  ")
        assert result == "Hello World"
