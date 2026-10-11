"""
Regression tests for the preferred-skill classification bug in JDMatcher.

Root cause (confirmed by execution):
  _extract_jd_skills() stored segment-local character positions in
  `classified_positions`. Two segments starting with ': ' cause skills
  at local offset 2 (e.g. Python at pos 2 in segment 2, Redis at pos 2
  in segment 4) to collide in the set. The second skill is incorrectly
  marked as already-classified and skipped by Pass 1; Pass 2 then picks
  it up and, seeing both REQUIRED and PREFERRED signals in its window,
  promotes it to required.

Fix verified:
  - Pass 1 now uses absolute character positions (seg_offset + local_pos).
  - Pass 2 uses proximity-based tie-breaking: the signal *closer* to the
    skill wins when both REQUIRED and PREFERRED are found in the window.

Run with:
    .venv/Scripts/python.exe -m pytest tests/test_preferred_skill_classification.py -v
"""

import os, sys, pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

SKILLS_JSON = os.path.join(PROJECT_ROOT, "data", "skills.json")


@pytest.fixture(scope="module")
def jd():
    if not os.path.exists(SKILLS_JSON):
        pytest.skip("skills.json not found")
    from modules.jd_matcher import JDMatcher
    return JDMatcher(SKILLS_JSON)


# ---------------------------------------------------------------------------
# Core regression — the original failure
# ---------------------------------------------------------------------------

class TestPreferredSkillClassificationBug:
    """
    Regression for: preferred skill classified as required when two
    colon-prefixed segments share the same local character offset.
    """

    RICH_JD = (
        "We need a backend engineer. "
        "Requirements: Python, Django, PostgreSQL, Docker, Git. "
        "Preferred: Redis, AWS, Kubernetes."
    )

    def test_redis_is_preferred_not_required(self, jd):
        """Redis appears after 'Preferred:' and must NOT end up in required."""
        result = jd.match(self.RICH_JD, [])
        req  = result["jd_skills"]["required"]
        pref = result["jd_skills"]["preferred"]
        assert "Redis" in pref, (
            f"Redis was misclassified as required. "
            f"required={req}, preferred={pref}"
        )
        assert "Redis" not in req, (
            f"Redis appeared in required. required={req}"
        )

    def test_redis_in_preferred_via_match(self, jd):
        """End-to-end: match() result places Redis in jd_preferred."""
        result = jd.match(self.RICH_JD, ["Python", "Django", "PostgreSQL", "Docker", "Git"])
        assert "Redis" in result["jd_skills"]["preferred"], (
            f"Redis not in preferred. preferred={result['jd_skills']['preferred']}, "
            f"required={result['jd_skills']['required']}"
        )
        assert "Redis" not in result["jd_skills"]["required"], (
            f"Redis incorrectly in required. required={result['jd_skills']['required']}"
        )

    def test_required_skills_unaffected(self, jd):
        """All five required skills must still be in required after the fix."""
        result = jd.match(self.RICH_JD, [])
        req_lower = [s.lower() for s in result["jd_skills"]["required"]]
        for skill in ["python", "django", "postgresql", "docker", "git"]:
            assert skill in req_lower, (
                f"'{skill}' missing from required. required={result['jd_skills']['required']}"
            )

    def test_score_with_all_required_matched(self, jd):
        """
        Resume matching all required skills should score >= 70%
        (required only contributes 70%, preferred adds up to 30%).
        Before the fix this scored 58.33%; after the fix it must be 70%+.
        """
        result = jd.match(self.RICH_JD, ["Python", "Django", "PostgreSQL", "Docker", "Git"])
        assert result["match_score"] >= 70.0, (
            f"Score with all required matched was {result['match_score']}, expected >= 70. "
            f"required={result['jd_skills']['required']}, preferred={result['jd_skills']['preferred']}"
        )

    def test_score_was_regressed_to_58_before_fix(self, jd):
        """
        Confirm the bug: with the old code the score was 58.33 because Redis
        was counted as required (denominator 6) and unmatched.
        With the fix the score must NOT be 58.33.
        """
        result = jd.match(self.RICH_JD, ["Python", "Django", "PostgreSQL", "Docker", "Git"])
        assert result["match_score"] != 58.33, (
            "Score is still 58.33 — the preferred-skill classification bug is not fixed."
        )

    def test_empty_resume_still_scores_zero(self, jd):
        """Empty resume against this JD must still score 0."""
        result = jd.match(self.RICH_JD, [])
        assert result["match_score"] == 0.0, (
            f"Empty resume scored {result['match_score']}, expected 0.0"
        )


# ---------------------------------------------------------------------------
# Edge cases — various section-header styles
# ---------------------------------------------------------------------------

class TestPreferredClassificationEdgeCases:

    def test_nice_to_have_section_classified_as_preferred(self, jd):
        """Skills under 'Nice to have:' must land in preferred."""
        text = (
            "We are hiring a Python developer. "
            "Requirements: Python, Django, PostgreSQL. "
            "Nice to have: Redis, Celery, RabbitMQ."
        )
        result = jd.match(text, [])
        pref_lower = [s.lower() for s in result["jd_skills"]["preferred"]]
        req_lower  = [s.lower() for s in result["jd_skills"]["required"]]
        assert "redis" in pref_lower, (
            f"Redis should be preferred (under 'Nice to have'). preferred={pref_lower}"
        )
        assert "redis" not in req_lower, (
            f"Redis incorrectly in required. required={req_lower}"
        )

    def test_bonus_section_classified_as_preferred(self, jd):
        """Skills under 'Bonus:' must land in preferred."""
        text = (
            "Backend Engineer opening. "
            "Required: Python, Node.js, MongoDB, Git. "
            "Bonus: AWS, Docker, Kubernetes."
        )
        result = jd.match(text, [])
        pref_lower = [s.lower() for s in result["jd_skills"]["preferred"]]
        req_lower  = [s.lower() for s in result["jd_skills"]["required"]]
        assert "aws" in pref_lower, (
            f"AWS should be preferred (under 'Bonus'). preferred={pref_lower}"
        )
        assert "aws" not in req_lower, (
            f"AWS incorrectly in required. required={req_lower}"
        )

    def test_desired_section_classified_as_preferred(self, jd):
        """Skills under 'Desired:' must land in preferred."""
        text = (
            "We are looking for a Full Stack Developer. "
            "Requirements: HTML, CSS, JavaScript, React, Git. "
            "Desired: TypeScript, Next.js, GraphQL."
        )
        result = jd.match(text, [])
        pref_lower = [s.lower() for s in result["jd_skills"]["preferred"]]
        req_lower  = [s.lower() for s in result["jd_skills"]["required"]]
        assert "typescript" in pref_lower, (
            f"TypeScript should be preferred (under 'Desired'). preferred={pref_lower}"
        )
        assert "typescript" not in req_lower, (
            f"TypeScript incorrectly in required. required={req_lower}"
        )

    def test_required_section_still_works_after_preferred(self, jd):
        """
        A JD with Preferred section BEFORE Required section must still
        classify skills correctly.
        """
        text = (
            "Data Scientist role. "
            "Preferred: Spark, Tableau, R. "
            "Requirements: Python, Pandas, NumPy, SQL, Machine Learning."
        )
        result = jd.match(text, [])
        req_lower  = [s.lower() for s in result["jd_skills"]["required"]]
        pref_lower = [s.lower() for s in result["jd_skills"]["preferred"]]
        assert "python" in req_lower, (
            f"Python should be required even with Preferred section first. required={req_lower}"
        )
        assert "pandas" in req_lower, f"Pandas not in required. required={req_lower}"
        assert "r" in pref_lower, (
            f"R should be preferred. preferred={pref_lower}"
        )

    def test_preferred_skills_count_toward_score(self, jd):
        """Matching preferred skills improves score beyond required-only."""
        text = (
            "Backend Engineer. "
            "Requirements: Python, Django, PostgreSQL, Git. "
            "Preferred: Redis, AWS."
        )
        # Resume with only required skills
        score_req_only = jd.match(text, ["Python", "Django", "PostgreSQL", "Git"])["match_score"]
        # Resume with required + preferred
        score_full     = jd.match(text, ["Python", "Django", "PostgreSQL", "Git", "Redis", "AWS"])["match_score"]
        assert score_full > score_req_only, (
            f"Matching preferred skills did not improve score. "
            f"req_only={score_req_only}, full={score_full}"
        )
        assert score_full == 100.0, (
            f"Full coverage (required + preferred) should score 100. Got {score_full}"
        )

    def test_preferred_only_jd_scores_correctly(self, jd):
        """
        A JD with only a preferred section (no required): full match = 100,
        empty resume = 0.
        """
        text = (
            "Nice to have: Python, Django, PostgreSQL, Redis, AWS, Docker. "
            "This is a junior role so requirements are flexible."
        )
        result_full  = jd.match(text, ["Python", "Django", "PostgreSQL", "Redis", "AWS", "Docker"])
        result_empty = jd.match(text, [])
        assert result_empty["match_score"] == 0.0, (
            f"Empty resume against preferred-only JD scored {result_empty['match_score']}"
        )
        assert result_full["match_score"] == 100.0, (
            f"Full-coverage resume against preferred-only JD scored {result_full['match_score']}"
        )

    def test_identical_local_offset_skills_in_different_sections(self, jd):
        """
        The original collision: two skills at local position 2 in different
        sections must each go to their own section, not collide.

        Pattern: both segments start with ': Skill' so local offset = 2.
        """
        text = (
            "Software Engineer. "
            "Requirements: React, Node.js, MongoDB, Git. "
            "Preferred: Redis, AWS, Docker."
        )
        result = jd.match(text, [])
        req_lower  = [s.lower() for s in result["jd_skills"]["required"]]
        pref_lower = [s.lower() for s in result["jd_skills"]["preferred"]]

        # React is the first-mentioned required skill (local pos 2 in segment 2)
        # Redis is the first-mentioned preferred skill (local pos 2 in segment 4)
        # They must NOT collide
        assert "react" in req_lower, f"React missing from required. required={req_lower}"
        assert "redis" in pref_lower, f"Redis missing from preferred. preferred={pref_lower}"
        assert "redis" not in req_lower, f"Redis incorrectly in required. required={req_lower}"
        assert "react" not in pref_lower, f"React incorrectly in preferred. preferred={pref_lower}"

    def test_proximity_tiebreak_prefers_nearer_signal(self, jd):
        """
        Pass 2 proximity tie-break: when a skill appears after a preferred
        section header with an earlier required section elsewhere in the
        short text, preferred signal wins because it is closer.
        """
        text = (
            "Requirements: Python, Django. "
            "Preferred: Redis, AWS."
        )
        result = jd.match(text, [])
        pref_lower = [s.lower() for s in result["jd_skills"]["preferred"]]
        req_lower  = [s.lower() for s in result["jd_skills"]["required"]]
        assert "redis" in pref_lower, (
            f"Redis should be preferred (closer to 'Preferred' than to 'Requirements'). "
            f"preferred={pref_lower}, required={req_lower}"
        )
        assert "python" in req_lower, f"Python should still be required. required={req_lower}"

    def test_no_skills_promoted_when_section_clear(self, jd):
        """
        When section headers are completely separate (no proximity overlap),
        every skill must be classified by its section, never promoted.
        """
        # Long enough that the required and preferred sections are > 200 chars apart
        padding = "x " * 110   # 220 chars of padding
        text = (
            f"Requirements: Python, Django. {padding}"
            f"Preferred: Redis, AWS."
        )
        result = jd.match(text, [])
        req_lower  = [s.lower() for s in result["jd_skills"]["required"]]
        pref_lower = [s.lower() for s in result["jd_skills"]["preferred"]]
        assert "python" in req_lower
        assert "django" in req_lower
        assert "redis" in pref_lower
        assert "aws" in pref_lower
        assert "redis" not in req_lower
        assert "aws" not in req_lower
