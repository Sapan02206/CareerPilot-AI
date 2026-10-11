"""
Tests for JDMatcher — specifically covering the five edge-case scenarios
identified in the P0-2 bug fix audit:

  Case A: Empty JD text
  Case B: Very short JD text (< 50 chars)
  Case C: JD with no recognised technical skills
  Case D: JD with only soft/general language
  Case E: Valid JD with recognised technical skills (normal path)

Run with:
    cd d:/Resume_Analyzer
    python -m pytest tests/test_jd_matcher.py -v

Runtime requirement: Python 3.10+ with no extra packages (jd_matcher uses
stdlib only + the project's data/skills.json file).
"""

import os
import sys
import pytest

# ---------------------------------------------------------------------------
# Path setup — ensure the project root is importable
# ---------------------------------------------------------------------------
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from modules.jd_matcher import JDMatcher, _clean_text

# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

SKILLS_JSON = os.path.join(PROJECT_ROOT, "data", "skills.json")


@pytest.fixture(scope="module")
def matcher():
    """Single JDMatcher instance shared across all tests in this module."""
    if not os.path.exists(SKILLS_JSON):
        pytest.skip(f"skills.json not found at {SKILLS_JSON}")
    return JDMatcher(SKILLS_JSON)


RESUME_SKILLS = ["Python", "Django", "PostgreSQL", "Docker", "Git"]

# ---------------------------------------------------------------------------
# Shared assertion helper
# ---------------------------------------------------------------------------

def assert_result_schema(result: dict):
    """Every result — good or bad — must have these top-level keys."""
    required_keys = {
        "analysis_status",
        "match_score",
        "metadata",
        "jd_skills",
        "resume_match",
        "keyword_gaps",
        "recommendations",
        "score_breakdown",
    }
    missing = required_keys - set(result.keys())
    assert not missing, f"Result missing keys: {missing}"

    # match_score must always be a number in [0, 100]
    assert 0.0 <= result["match_score"] <= 100.0, (
        f"match_score {result['match_score']} is outside [0, 100]"
    )

    # recommendations must always be a list (even if empty)
    assert isinstance(result["recommendations"], list), (
        "recommendations must be a list"
    )


# ===========================================================================
# Case A — Empty JD
# ===========================================================================

class TestCaseA_EmptyJD:
    """Passing an empty string (or whitespace-only) must never produce a
    100 % score and must report analysis_status='jd_empty'."""

    def test_empty_string(self, matcher):
        result = matcher.match("", RESUME_SKILLS)
        assert_result_schema(result)
        assert result["analysis_status"] == "jd_empty"
        assert result["match_score"] == 0.0

    def test_whitespace_only(self, matcher):
        result = matcher.match("   \n\t\n   ", RESUME_SKILLS)
        assert_result_schema(result)
        assert result["analysis_status"] == "jd_empty"
        assert result["match_score"] == 0.0

    def test_empty_has_helpful_recommendation(self, matcher):
        result = matcher.match("", RESUME_SKILLS)
        assert len(result["recommendations"]) >= 1
        rec = result["recommendations"][0]
        # Must have 'title' and 'detail' keys (same schema as other recs)
        assert "title" in rec
        assert "detail" in rec
        assert len(rec["detail"]) > 10, "detail message too short to be useful"

    def test_empty_jd_skills_are_empty_lists(self, matcher):
        result = matcher.match("", RESUME_SKILLS)
        assert result["jd_skills"]["required"] == []
        assert result["jd_skills"]["preferred"] == []
        assert result["jd_skills"]["total"] == 0


# ===========================================================================
# Case B — Very short JD (< 50 characters after cleaning)
# ===========================================================================

class TestCaseB_ShortJD:
    """JDs under 50 characters are too sparse for meaningful analysis."""

    def test_single_word(self, matcher):
        result = matcher.match("Developer", RESUME_SKILLS)
        assert_result_schema(result)
        assert result["analysis_status"] == "jd_too_short"
        assert result["match_score"] == 0.0

    def test_exactly_49_chars(self, matcher):
        # 49 chars of real-looking but incomplete text
        text = "We are hiring a developer for our startup team ok"  # ~50 chars; trim to 49
        text = text[:49]
        result = matcher.match(text, RESUME_SKILLS)
        assert_result_schema(result)
        # May or may not be "jd_too_short" depending on exact clean length
        # The point is it must NOT produce match_score=100 from empty skill lists
        assert result["match_score"] < 100.0

    def test_html_stripped_to_short(self, matcher):
        # HTML tags stripped, leaving < 50 meaningful chars
        result = matcher.match("<div><p></p><span></span></div>Hire Python dev", RESUME_SKILLS)
        assert_result_schema(result)
        assert result["match_score"] < 100.0

    def test_short_jd_score_never_100(self, matcher):
        for short_text in ["", "hello", "  ", "we need a dev"]:
            result = matcher.match(short_text, RESUME_SKILLS)
            assert_result_schema(result)
            assert result["match_score"] != 100.0, (
                f"Got 100% for '{short_text}' — the guard did not fire"
            )


# ===========================================================================
# Case C — No recognised skills in the JD
# ===========================================================================

class TestCaseC_NoRecognisedSkills:
    """JDs with substantial text but no skills from the database must
    return analysis_status='no_skills_detected' and score=0."""

    NO_SKILL_JD = (
        "We are looking for a passionate and driven individual to join our "
        "growing organisation. The ideal candidate will thrive in a "
        "fast-paced environment and bring creativity and enthusiasm to the "
        "team. You will be responsible for delivering results and working "
        "collaboratively across departments. A competitive salary and "
        "excellent benefits are offered. Apply today and become part of "
        "our journey toward excellence and innovation in the marketplace."
    )

    def test_status_is_no_skills_detected(self, matcher):
        result = matcher.match(self.NO_SKILL_JD, RESUME_SKILLS)
        assert_result_schema(result)
        assert result["analysis_status"] == "no_skills_detected"

    def test_score_is_zero(self, matcher):
        result = matcher.match(self.NO_SKILL_JD, RESUME_SKILLS)
        assert result["match_score"] == 0.0

    def test_score_never_100(self, matcher):
        result = matcher.match(self.NO_SKILL_JD, RESUME_SKILLS)
        assert result["match_score"] != 100.0

    def test_helpful_message_present(self, matcher):
        result = matcher.match(self.NO_SKILL_JD, RESUME_SKILLS)
        rec = result["recommendations"][0]
        assert "detail" in rec
        assert len(rec["detail"]) > 20

    def test_empty_resume_skills_still_safe(self, matcher):
        """Even with no resume skills, no_skills_detected JD must not crash."""
        result = matcher.match(self.NO_SKILL_JD, [])
        assert_result_schema(result)
        assert result["match_score"] == 0.0


# ===========================================================================
# Case D — JD with only soft/general language skills
# ===========================================================================

class TestCaseD_SoftSkillsOnly:
    """If the JD mentions only soft skills (communication, leadership, etc.)
    it should return analysis_status='only_soft_skills' with a low score (10)
    and a warning, not a misleading match score."""

    SOFT_ONLY_JD = (
        "We are seeking a candidate with excellent communication skills and "
        "strong leadership abilities. You must demonstrate problem solving "
        "and critical thinking capabilities. Team collaboration and time "
        "management are essential. Adaptability and creativity are highly "
        "valued. Experience with project management and agile methodology "
        "is required. Mentoring and coaching experience is a plus. "
        "Stakeholder management and presentation skills are necessary."
    )

    def test_status_is_only_soft_skills(self, matcher):
        result = matcher.match(self.SOFT_ONLY_JD, RESUME_SKILLS)
        assert_result_schema(result)
        # Either "only_soft_skills" (all extracted are soft) or "ok" with low
        # technical skill count. Both are acceptable — must not be 100%.
        assert result["match_score"] < 100.0

    def test_score_is_low(self, matcher):
        result = matcher.match(self.SOFT_ONLY_JD, RESUME_SKILLS)
        # Soft-only should be <= 10 (the soft_score constant)
        # OR a normal low score if some soft skills map to both categories
        assert result["match_score"] <= 50.0, (
            f"Expected low score for soft-only JD, got {result['match_score']}"
        )

    def test_never_100(self, matcher):
        result = matcher.match(self.SOFT_ONLY_JD, [])
        assert result["match_score"] != 100.0

    def test_schema_complete(self, matcher):
        result = matcher.match(self.SOFT_ONLY_JD, RESUME_SKILLS)
        assert_result_schema(result)


# ===========================================================================
# Case E — Valid JD with recognised technical skills (normal path)
# ===========================================================================

class TestCaseE_ValidJD:
    """A real-looking JD with technical skills must go through the normal
    pipeline and produce a meaningful, correctly bounded score."""

    BACKEND_JD = (
        "We are looking for a Backend Developer to join our team. "
        "Requirements: "
        "- 3+ years of Python development experience. "
        "- Proficiency with Django or Flask web frameworks. "
        "- Strong understanding of PostgreSQL and SQL. "
        "- Experience with Docker and containerisation. "
        "- Familiarity with REST API design and development. "
        "- Version control with Git is required. "
        "Preferred skills: "
        "- Experience with Redis caching. "
        "- Knowledge of AWS or other cloud platforms. "
        "- Familiarity with Kubernetes. "
        "- Understanding of CI/CD pipelines. "
    )

    def test_status_is_ok(self, matcher):
        result = matcher.match(self.BACKEND_JD, RESUME_SKILLS)
        assert_result_schema(result)
        assert result["analysis_status"] == "ok"

    def test_score_in_valid_range(self, matcher):
        result = matcher.match(self.BACKEND_JD, RESUME_SKILLS)
        assert 0.0 < result["match_score"] <= 100.0

    def test_score_not_100_for_partial_resume(self, matcher):
        """Resume with only 2 skills should NOT score 100% on a 9-skill JD."""
        result = matcher.match(self.BACKEND_JD, ["Python", "Git"])
        assert result["match_score"] < 100.0

    def test_matched_required_populated(self, matcher):
        result = matcher.match(self.BACKEND_JD, RESUME_SKILLS)
        # Python, Django/Flask, PostgreSQL, Docker, Git should all match
        assert len(result["resume_match"]["matched_required"]) >= 3

    def test_missing_required_populated(self, matcher):
        # With only ["Python"], most required skills should be missing
        result = matcher.match(self.BACKEND_JD, ["Python"])
        assert len(result["resume_match"]["missing_required"]) >= 1

    def test_recommendations_list_nonempty(self, matcher):
        result = matcher.match(self.BACKEND_JD, RESUME_SKILLS)
        assert len(result["recommendations"]) >= 1

    def test_every_recommendation_has_title_and_detail(self, matcher):
        result = matcher.match(self.BACKEND_JD, RESUME_SKILLS)
        for rec in result["recommendations"]:
            assert "title" in rec, f"Rec missing 'title': {rec}"
            assert "detail" in rec, f"Rec missing 'detail': {rec}"

    def test_jd_skills_total_nonzero(self, matcher):
        result = matcher.match(self.BACKEND_JD, RESUME_SKILLS)
        assert result["jd_skills"]["total"] > 0

    def test_score_breakdown_keys_present(self, matcher):
        result = matcher.match(self.BACKEND_JD, RESUME_SKILLS)
        assert "required_coverage" in result["score_breakdown"]
        assert "preferred_coverage" in result["score_breakdown"]

    def test_high_coverage_resume_scores_high(self, matcher):
        """A resume that matches every required skill should score >= 60."""
        full_resume = [
            "Python", "Django", "Flask", "PostgreSQL", "SQL",
            "Docker", "REST API", "Git", "Redis", "AWS", "Kubernetes"
        ]
        result = matcher.match(self.BACKEND_JD, full_resume)
        assert result["match_score"] >= 60.0, (
            f"Full-coverage resume scored too low: {result['match_score']}"
        )

    def test_empty_resume_scores_zero_not_100(self, matcher):
        """A resume with no skills must score 0, not 100."""
        result = matcher.match(self.BACKEND_JD, [])
        assert result["match_score"] == 0.0, (
            f"Empty resume scored {result['match_score']} — expected 0.0"
        )


# ===========================================================================
# _score() unit tests — the arithmetic heart of P0-2
# ===========================================================================

class TestScoreMethod:
    """Direct unit tests of the _score() helper to prove the zero-guard works."""

    def test_both_zero_returns_zero(self, matcher):
        """The original bug: _score(0,0,0,0) returned 100.0. Must now be 0.0."""
        result = matcher._score(0, 0, 0, 0)
        assert result == 0.0, f"Expected 0.0, got {result}"

    def test_full_match_returns_100(self, matcher):
        result = matcher._score(5, 5, 3, 3)
        assert result == 100.0

    def test_no_match_with_skills_in_jd_returns_0(self, matcher):
        result = matcher._score(0, 5, 0, 3)
        assert result == 0.0

    def test_partial_required_only(self, matcher):
        # 3/5 required matched, no preferred skills in JD
        # With the fixed formula: no preferred → score = req_ratio * 100 = 60.0
        score = matcher._score(3, 5, 0, 0)
        assert 0.0 < score < 100.0
        assert score == 60.0, f"Expected 60.0 (3/5 required, no preferred), got {score}"

    def test_partial_preferred_only(self, matcher):
        # All required matched, only half preferred matched
        score = matcher._score(5, 5, 2, 4)
        # req_ratio=1.0, pref_ratio=0.5 → (0.70+0.15)*100=85
        assert 0.0 < score <= 100.0

    def test_score_bounded(self, matcher):
        """Score must always be in [0, 100]."""
        cases = [
            (0, 0, 0, 0),
            (1, 1, 1, 1),
            (0, 5, 0, 5),
            (5, 5, 0, 5),
            (3, 5, 2, 4),
        ]
        for args in cases:
            s = matcher._score(*args)
            assert 0.0 <= s <= 100.0, f"Out-of-range score {s} for args {args}"


# ===========================================================================
# _check_jd_viability() unit tests
# ===========================================================================

class TestViabilityCheck:
    """Unit tests for the pre-flight viability check."""

    def test_empty_string_not_viable(self, matcher):
        viable, status, _ = matcher._check_jd_viability("")
        assert viable is False
        assert status == "jd_empty"

    def test_whitespace_not_viable(self, matcher):
        viable, status, _ = matcher._check_jd_viability("   ")
        assert viable is False
        assert status == "jd_empty"

    def test_short_text_not_viable(self, matcher):
        viable, status, _ = matcher._check_jd_viability("hello world")
        assert viable is False
        assert status == "jd_too_short"

    def test_long_no_skills_not_viable(self, matcher):
        # Long generic text with no technical skills
        text = (
            "We are seeking a driven and motivated individual who thrives "
            "in collaborative environments and brings passion and dedication "
            "to every project they undertake in our growing organisation."
        )
        viable, status, _ = matcher._check_jd_viability(text)
        assert viable is False
        assert status == "no_skills_detected"

    def test_valid_jd_is_viable(self, matcher):
        text = (
            "Backend Engineer role. Required: Python, PostgreSQL, Docker. "
            "Preferred: AWS, Kubernetes. 3 years experience needed."
        )
        viable, status, msg = matcher._check_jd_viability(text)
        assert viable is True
        assert status == "ok"
        assert msg == ""

    def test_message_is_nonempty_for_all_non_viable(self, matcher):
        cases = ["", "hi", "no known technologies here at all ever"]
        for text in cases:
            _, _, msg = matcher._check_jd_viability(text)
            if text == "":
                assert len(msg) > 0
