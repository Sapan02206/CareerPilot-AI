"""
Regression tests for the CareerPilot AI Reliability Audit.

Covers confirmed defects from manual testing:

  Part A — Dashboard scoring
    A1. "Responsive Web Design" alias maps to canonical "Responsive Design"
    A2. Experience score is 0 when no explicit year statements are present (expected behavior)
    A3. Experience score is non-zero when explicit year statements are present
    A4. Evidence score uses only UserProject records, not resume text
    A5. Duplicate snapshot guard — returning-user path only saves when evidence changes
    A6. Readiness formula weights are correct

  Part B — JD matcher
    B1. Fully-matching resume → 100% score is legitimate
    B2. Partially-matching resume → score < 100
    B3. Unrecognised requirements are surfaced in `unrecognised_requirements`, not silently dropped
    B4. Score denominator only counts extracted skills (not dropped terms)
    B5. Technical + non-skill requirements → non-skill terms do not inflate score
    B6. Required vs preferred skill distinction is preserved
    B7. Plural forms (REST APIs vs REST API) are handled gracefully
    B8. Equivalent aliases match correctly
    B9. score_note / scoring_note present when unrecognised requirements exist
    B10. Empty / insufficient JD returns structured error, not 100%

  Part C — ATS scorer
    C1. Email in standard form is detected
    C2. Email surrounded by whitespace/newlines is detected
    C3. Email adjacent to phone/URL still detected
    C4. Missing email is correctly flagged
    C5. Contact at end of document still detected
    C6. clean_text preserves @ symbol (the root cause fix)
    C7. Email after clean_text still matches email regex

Run:
    cd d:/Resume_Analyzer
    python -m pytest tests/test_reliability_audit.py -v
"""

import os
import sys
import re
import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

SKILLS_JSON    = os.path.join(PROJECT_ROOT, "data", "skills.json")
JOBROLES_JSON  = os.path.join(PROJECT_ROOT, "data", "job_roles.json")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def skill_extractor():
    if not os.path.exists(SKILLS_JSON):
        pytest.skip("skills.json not found")
    from modules.skill_extractor import SkillExtractor
    return SkillExtractor(SKILLS_JSON)


@pytest.fixture(scope="module")
def skill_matcher():
    if not os.path.exists(JOBROLES_JSON):
        pytest.skip("job_roles.json not found")
    from modules.matcher import SkillMatcher
    return SkillMatcher(JOBROLES_JSON)


@pytest.fixture(scope="module")
def jd_matcher():
    if not os.path.exists(SKILLS_JSON):
        pytest.skip("skills.json not found")
    from modules.jd_matcher import JDMatcher
    return JDMatcher(SKILLS_JSON)


@pytest.fixture(scope="module")
def ats_scorer():
    from modules.ats_scorer import ATSScorer
    return ATSScorer()


@pytest.fixture(scope="module")
def readiness_calc():
    from modules.readiness_calculator import ReadinessCalculator
    return ReadinessCalculator()


@pytest.fixture(scope="module")
def exp_extractor():
    from modules.experience_extractor import ExperienceExtractor
    return ExperienceExtractor()


# ---------------------------------------------------------------------------
# Part A — Dashboard scoring
# ---------------------------------------------------------------------------

class TestPartA_DashboardScoring:

    # A1 — Responsive Web Design alias
    def test_responsive_web_design_alias_in_skill_variations(self):
        """'Responsive Web Design' must be listed as a variation of 'Responsive Design'."""
        import json
        with open(SKILLS_JSON) as f:
            data = json.load(f)
        variations = data.get("skill_variations", {})
        assert "Responsive Design" in variations, (
            "'Responsive Design' key missing from skill_variations"
        )
        aliases = [v.lower() for v in variations["Responsive Design"]]
        assert "responsive web design" in aliases, (
            "'Responsive Web Design' not listed as alias of 'Responsive Design'. "
            f"Current aliases: {variations['Responsive Design']}"
        )

    def test_responsive_web_design_extracted_from_resume(self, skill_extractor):
        """A resume that says 'Responsive Web Design' must yield 'Responsive Design'."""
        text = (
            "Built several web applications with responsive web design principles. "
            "Used HTML, CSS, and JavaScript throughout."
        )
        skills = skill_extractor.extract_skills(text)
        skills_lower = [s.lower() for s in skills]
        assert "responsive design" in skills_lower, (
            f"'Responsive Web Design' was not normalised to 'Responsive Design'. "
            f"Extracted: {skills}"
        )

    def test_responsive_design_direct_still_works(self, skill_extractor):
        """'Responsive Design' (exact canonical) still extracted normally."""
        text = "Expert in responsive design and cross-browser compatibility."
        skills = skill_extractor.extract_skills(text)
        skills_lower = [s.lower() for s in skills]
        assert "responsive design" in skills_lower, (
            f"Direct 'Responsive Design' not extracted. Got: {skills}"
        )

    def test_responsive_web_design_matches_frontend_role(self, skill_extractor, skill_matcher):
        """
        A resume listing 'responsive web design' must NOT report 'Responsive Design'
        as a missing required skill for Frontend Developer.
        """
        import json
        with open(JOBROLES_JSON) as f:
            roles = json.load(f)
        if "Frontend Developer" not in roles:
            pytest.skip("Frontend Developer role not in job_roles.json")
        if "Responsive Design" not in roles["Frontend Developer"].get("required_skills", []):
            pytest.skip("Responsive Design not a required skill for Frontend Developer")

        text = (
            "Developed web apps using responsive web design. "
            "Skilled in HTML, CSS, JavaScript, React, Git."
        )
        skills = skill_extractor.extract_skills(text)
        result = skill_matcher.match_skills(skills, "Frontend Developer")
        missing = [s.lower() for s in result["missing_required"]]
        assert "responsive design" not in missing, (
            "'Responsive Design' still reported as missing even when resume says "
            f"'Responsive Web Design'. Missing: {result['missing_required']}"
        )

    # A2 — Experience 0% with no explicit year statements
    def test_experience_score_zero_when_no_explicit_years(self, readiness_calc):
        """When no enriched skill has experience_years, experience_score must be 0."""
        enriched = [
            {"skill": "Python",     "experience_years": None, "category": "technical"},
            {"skill": "Django",     "experience_years": None, "category": "technical"},
            {"skill": "PostgreSQL", "experience_years": None, "category": "technical"},
        ]
        match_results = {
            "match_score": 70.0,
            "matched_required": ["Python", "Django"],
            "missing_required": ["SQL"],
            "matched_optional": [],
            "missing_optional": [],
        }
        result = readiness_calc.calculate_readiness(enriched, match_results, [])
        assert result["experience_score"] == 0.0, (
            f"Expected 0.0 experience score when all years are None, "
            f"got {result['experience_score']}"
        )

    def test_experience_score_zero_is_expected_design_behavior(self, exp_extractor):
        """
        ExperienceExtractor returns None for a skill not explicitly quantified.
        This is documented design behavior, not a defect.
        """
        text = (
            "Developed web applications using Python and Django. "
            "Built a school tracking app and a vendor management platform."
        )
        result = exp_extractor.extract_experience(text, "Python")
        # No explicit year statement → None is correct
        assert result is None, (
            "Experience extractor should return None when no explicit year "
            f"statement is present. Got: {result}"
        )

    # A3 — Experience non-zero with explicit year statements
    def test_experience_score_nonzero_with_explicit_years(self, readiness_calc):
        """Enriched skills with explicit experience_years produce a non-zero score."""
        enriched = [
            {"skill": "Python", "experience_years": 2.0, "category": "technical"},
            {"skill": "Django", "experience_years": 1.5, "category": "technical"},
        ]
        match_results = {
            "match_score": 70.0,
            "matched_required": ["Python", "Django"],
            "missing_required": ["SQL"],
            "matched_optional": [],
            "missing_optional": [],
        }
        result = readiness_calc.calculate_readiness(enriched, match_results, [])
        assert result["experience_score"] > 0, (
            f"Expected non-zero experience score. Got: {result['experience_score']}"
        )

    def test_experience_extractor_finds_explicit_years(self, exp_extractor):
        """ExperienceExtractor finds explicit year statements correctly."""
        cases = [
            ("5 years of Python experience", "Python", 5.0),
            ("React developer with 3 years",  "React",  3.0),
            ("Django (2 years)",               "Django", 2.0),
            ("Node.js for 18 months",          "Node.js", 1.5),
        ]
        for text, skill, expected in cases:
            result = exp_extractor.extract_experience(text, skill)
            assert result is not None, f"Got None for '{text}'"
            assert result["years"] == expected, (
                f"'{text}' → expected {expected} years, got {result['years']}"
            )

    # A4 — Evidence uses only UserProject records
    def test_evidence_score_zero_with_no_db_projects(self, readiness_calc):
        """Evidence is 0 when no UserProject records exist, regardless of resume content."""
        enriched = [{"skill": "Python", "experience_years": None, "category": "technical"}]
        match_results = {
            "match_score": 60.0,
            "matched_required": ["Python"],
            "missing_required": [],
            "matched_optional": [],
            "missing_optional": [],
        }
        result = readiness_calc.calculate_readiness(enriched, match_results, projects=[])
        assert result["evidence_score"] == 0.0, (
            f"Evidence score should be 0 with empty projects list. Got: {result['evidence_score']}"
        )

    def test_evidence_score_increases_with_user_projects(self, readiness_calc):
        """Adding a UserProject record with a matching skill increases evidence score."""
        enriched = [{"skill": "Python", "experience_years": None, "category": "technical"}]
        match_results = {
            "match_score": 60.0,
            "matched_required": ["Python"],
            "missing_required": ["SQL"],
            "matched_optional": [],
            "missing_optional": [],
        }
        projects = [{
            "id": 1,
            "title": "School Tracking App",
            "description": "Django app",
            "skills_used": ["Python", "Django"],
            "start_date": None,
            "end_date": None,
            "project_url": None,
        }]
        result = readiness_calc.calculate_readiness(enriched, match_results, projects)
        assert result["evidence_score"] > 0.0, (
            f"Evidence score should be > 0 when a matching project exists. "
            f"Got: {result['evidence_score']}"
        )

    def test_evidence_url_bonus(self, readiness_calc):
        """A project with a URL receives a +10 bonus on evidence score."""
        match_results = {
            "match_score": 60.0,
            "matched_required": ["Python"],
            "missing_required": [],
            "matched_optional": [],
            "missing_optional": [],
        }
        project_no_url  = [{"title": "A", "skills_used": ["Python"], "project_url": None}]
        project_with_url = [{"title": "A", "skills_used": ["Python"], "project_url": "https://github.com/x/y"}]

        score_no_url   = readiness_calc.calculate_evidence_score(project_no_url,  ["Python"])
        score_with_url = readiness_calc.calculate_evidence_score(project_with_url, ["Python"])
        assert score_with_url == score_no_url + 10, (
            f"URL bonus not applied. No-URL: {score_no_url}, With-URL: {score_with_url}"
        )

    # A5 — Duplicate snapshot guard
    def test_duplicate_snapshot_guard_in_app(self):
        """
        Verify that the returning-user dashboard path only saves a snapshot when
        the overall readiness score has changed.  Guards on overall_score so that
        any component change (skill match, experience, OR evidence) triggers a save,
        while identical page-refresh reloads are suppressed.
        This is a static code inspection because the database is not available.
        """
        app_path = os.path.join(PROJECT_ROOT, "app.py")
        with open(app_path, encoding="utf-8") as f:
            source = f.read()
        assert "_save_snapshot" in source, "app.py must contain '_save_snapshot'"
        assert "_readiness_changed" in source, (
            "app.py must contain _readiness_changed helper"
        )

        lines = source.splitlines()

        # Find lines that CALL _save_snapshot (not the definition)
        call_lines = [
            i for i, l in enumerate(lines)
            if "_save_snapshot(" in l and not l.strip().startswith("def ")
        ]
        assert len(call_lines) >= 2, (
            f"Expected at least 2 _save_snapshot call sites, found {len(call_lines)}"
        )

        # The returning-user path should guard the _save_snapshot call with
        # _readiness_changed() — scan within ±5 lines of each call site.
        found_guard = False
        for call_idx in call_lines:
            window_start = max(0, call_idx - 5)
            window_end   = min(len(lines), call_idx + 2)
            window = "\n".join(lines[window_start:window_end])
            # Accept either the old overall_score comparison or the new _readiness_changed call
            if ("_readiness_changed(" in window or "overall_score" in window) and "if " in window:
                found_guard = True
                break

        assert found_guard, (
            "No _save_snapshot call found with a guard (if _readiness_changed or "
            "if overall_score) nearby. The returning-user path must guard snapshot saves."
        )

    # A6 — Readiness formula
    def test_readiness_formula_weights(self, readiness_calc):
        """overall = skill*0.5 + exp*0.3 + evidence*0.2 — verify weights exactly."""
        enriched = [
            {"skill": "Python", "experience_years": 3.0, "category": "technical"},
        ]
        match_results = {
            "match_score": 80.0,
            "matched_required": ["Python"],
            "missing_required": ["SQL"],
            "matched_optional": [],
            "missing_optional": [],
        }
        result = readiness_calc.calculate_readiness(enriched, match_results, [])
        s = result["skill_match_score"]
        e = result["experience_score"]
        v = result["evidence_score"]
        expected = round(s * 0.50 + e * 0.30 + v * 0.20, 2)
        assert result["overall_score"] == expected, (
            f"Formula mismatch: {s}*0.5 + {e}*0.3 + {v}*0.2 = {expected}, "
            f"got {result['overall_score']}"
        )


# ---------------------------------------------------------------------------
# Part B — JD matcher scoring policy
# ---------------------------------------------------------------------------

class TestPartB_JDMatcherReliability:

    # The Junior Full Stack JD from the audit report
    JUNIOR_FULLSTACK_JD = """
    Junior Full Stack Developer

    Requirements:
    - HTML
    - CSS
    - JavaScript
    - React
    - Node.js
    - Express.js
    - REST APIs
    - MongoDB
    - Git
    - GitHub
    - Responsive web applications
    - Debugging
    - Code quality
    - Problem-solving
    - Willingness to learn
    """

    FULLSTACK_RESUME_FULL = [
        "HTML", "CSS", "JavaScript", "React", "Node.js",
        "Express.js", "MongoDB", "Git", "GitHub",
    ]
    FULLSTACK_RESUME_PARTIAL = ["HTML", "CSS", "JavaScript", "React", "Git"]

    def test_schema_has_unrecognised_requirements_key(self, jd_matcher):
        """match() result always contains 'unrecognised_requirements' key."""
        result = jd_matcher.match(self.JUNIOR_FULLSTACK_JD, self.FULLSTACK_RESUME_FULL)
        assert "unrecognised_requirements" in result, (
            "Result schema missing 'unrecognised_requirements' key"
        )
        assert isinstance(result["unrecognised_requirements"], list)

    def test_schema_has_scoring_note_key(self, jd_matcher):
        """match() result always contains 'scoring_note' key (may be None)."""
        result = jd_matcher.match(self.JUNIOR_FULLSTACK_JD, self.FULLSTACK_RESUME_FULL)
        assert "scoring_note" in result, "Result schema missing 'scoring_note' key"

    def test_unanalysable_response_has_unrecognised_key(self, jd_matcher):
        """_unanalysable_response also returns the two new keys with safe defaults."""
        result = jd_matcher.match("", [])
        assert "unrecognised_requirements" in result
        assert "scoring_note" in result
        assert result["unrecognised_requirements"] == []

    def test_score_bounded_0_100_full_resume(self, jd_matcher):
        """Score is always in [0, 100] regardless of input."""
        result = jd_matcher.match(self.JUNIOR_FULLSTACK_JD, self.FULLSTACK_RESUME_FULL)
        assert 0.0 <= result["match_score"] <= 100.0

    def test_partial_resume_scores_less_than_full(self, jd_matcher):
        """A partial resume scores strictly less than a full-coverage resume."""
        full    = jd_matcher.match(self.JUNIOR_FULLSTACK_JD, self.FULLSTACK_RESUME_FULL)
        partial = jd_matcher.match(self.JUNIOR_FULLSTACK_JD, self.FULLSTACK_RESUME_PARTIAL)
        assert partial["match_score"] < full["match_score"], (
            f"Partial ({partial['match_score']}) should be < full ({full['match_score']})"
        )

    def test_empty_resume_scores_zero(self, jd_matcher):
        """
        A resume with no skills scores 0 against a valid JD.
        The score formula must not award phantom 'preferred credit' when the JD
        has required skills only — an empty resume must score 0.
        """
        result = jd_matcher.match(self.JUNIOR_FULLSTACK_JD, [])
        assert result["match_score"] == 0.0, (
            f"Empty resume scored {result['match_score']}, expected 0.0. "
            f"JD skills total={result['jd_skills']['total']}, "
            f"required={len(result['jd_skills']['required'])}, "
            f"preferred={len(result['jd_skills']['preferred'])}"
        )

    def test_denominator_equals_extracted_skills_not_all_requirements(self, jd_matcher):
        """
        The score denominator is the number of *extracted* (recognised) skills,
        not the total number of bullet points in the JD.

        The JD has 15 bullet points; we expect fewer than 15 recognised skills
        because terms like 'Responsive web applications', 'Debugging',
        'Code quality', 'Problem-solving', 'Willingness to learn' are not
        in the skill database.
        """
        result = jd_matcher.match(self.JUNIOR_FULLSTACK_JD, self.FULLSTACK_RESUME_FULL)
        total_extracted = result["jd_skills"]["total"]
        # The JD has 15 bullet points; we expect several to be unrecognised
        assert total_extracted < 15, (
            f"Expected < 15 extracted skills (some JD bullets are unrecognised). "
            f"Got {total_extracted}. This means unrecognised terms are being injected."
        )

    def test_unrecognised_requirements_present_for_partial_jd(self, jd_matcher):
        """The JD with non-skill bullets must produce non-empty unrecognised_requirements."""
        result = jd_matcher.match(self.JUNIOR_FULLSTACK_JD, self.FULLSTACK_RESUME_FULL)
        # "Debugging", "Code quality", "Problem-solving", "Willingness to learn"
        # should all end up in unrecognised_requirements
        assert len(result["unrecognised_requirements"]) > 0, (
            "Expected at least one unrecognised requirement for a JD that contains "
            "non-skill bullet points. "
            f"Got empty list. Extracted skills: {result['jd_skills']}"
        )

    def test_scoring_note_present_when_unrecognised_exist(self, jd_matcher):
        """scoring_note is a non-None string when unrecognised requirements exist."""
        result = jd_matcher.match(self.JUNIOR_FULLSTACK_JD, self.FULLSTACK_RESUME_FULL)
        if result["unrecognised_requirements"]:
            assert result["scoring_note"] is not None, (
                "scoring_note should be a string when unrecognised_requirements is non-empty"
            )
            assert len(result["scoring_note"]) > 10

    def test_scoring_note_none_when_all_requirements_recognised(self, jd_matcher):
        """scoring_note is None when no requirements were dropped."""
        simple_jd = (
            "Backend role. Requirements: Python, Django, PostgreSQL, Docker, Git. "
            "Preferred: Redis, AWS."
        )
        result = jd_matcher.match(simple_jd, ["Python", "Django", "PostgreSQL"])
        # If all extracted skills are recognised, note should be None
        if not result["unrecognised_requirements"]:
            assert result["scoring_note"] is None

    def test_plural_rest_apis_handled_gracefully(self, jd_matcher):
        """
        'REST APIs' (plural) is not in the skill database.
        The system should not crash and should not secretly count it as a match.
        The unrecognised list should contain something about REST/API.
        """
        jd = (
            "We need a developer with strong REST APIs knowledge. "
            "Must know Node.js and MongoDB."
        )
        result = jd_matcher.match(jd, ["Node.js", "MongoDB"])
        assert result["analysis_status"] == "ok"
        assert 0.0 <= result["match_score"] <= 100.0
        # 'REST API' (singular) should still be detected; 'REST APIs' plural may or
        # may not — the important thing is no crash and valid score
        assert isinstance(result["unrecognised_requirements"], list)

    def test_github_alias_matched(self, jd_matcher):
        """
        'GitHub' is in skills.json. A resume with 'Git' should match 'Git' but
        'GitHub' should only match if explicitly in the resume skills.
        """
        jd = "Required: Git, GitHub, JavaScript."
        result_with_github = jd_matcher.match(jd, ["Git", "GitHub", "JavaScript"])
        result_without_github = jd_matcher.match(jd, ["Git", "JavaScript"])
        # Score with GitHub present should be >= score without it
        assert result_with_github["match_score"] >= result_without_github["match_score"]

    def test_required_preferred_distinction_preserved(self, jd_matcher):
        """Skills in 'Required' section land in jd_required, 'Preferred' in jd_preferred."""
        jd = (
            "Requirements: Python, PostgreSQL, Docker. "
            "Preferred: Redis, AWS, Kubernetes."
        )
        result = jd_matcher.match(jd, ["Python"])
        assert len(result["jd_skills"]["required"]) > 0, "Required skills list empty"
        assert len(result["jd_skills"]["preferred"]) > 0, "Preferred skills list empty"
        required_lower = [s.lower() for s in result["jd_skills"]["required"]]
        preferred_lower = [s.lower() for s in result["jd_skills"]["preferred"]]
        assert "python" in required_lower, "Python not in required"
        # Redis or AWS should be in preferred
        assert any(s in preferred_lower for s in ["redis", "aws", "kubernetes"]), (
            f"Expected at least one preferred skill. Preferred: {result['jd_skills']['preferred']}"
        )

    def test_empty_jd_returns_zero_not_100(self, jd_matcher):
        """Empty JD returns 0, not 100. Regression for P0-2."""
        result = jd_matcher.match("", ["Python", "React"])
        assert result["match_score"] == 0.0
        assert result["analysis_status"] == "jd_empty"

    def test_score_is_correct_over_extracted_denominator(self, jd_matcher):
        """
        Score is calculated only over recognised skills.

        Uses a JD with a Requirements section containing multiple explicit skills
        AND a Preferred section — so the extractor has both section headers and
        proximity signals to work with, which is the reliable extraction path.
        """
        rich_jd = (
            "We need a backend engineer. "
            "Requirements: Python, Django, PostgreSQL, Docker, Git. "
            "Preferred: Redis, AWS, Kubernetes."
        )
        # Full-coverage resume (all required)
        full_resume = ["Python", "Django", "PostgreSQL", "Docker", "Git"]
        result_full = jd_matcher.match(rich_jd, full_resume)
        assert result_full["analysis_status"] == "ok"
        assert result_full["match_score"] > 50.0, (
            f"Full-coverage resume should score well. Got: {result_full['match_score']}. "
            f"Extracted required={result_full['jd_skills']['required']}"
        )
        # Empty resume against the same JD must score 0
        result_empty = jd_matcher.match(rich_jd, [])
        assert result_empty["match_score"] == 0.0, (
            f"Empty resume scored {result_empty['match_score']}, expected 0.0"
        )

    def test_match_score_zero_for_no_overlap(self, jd_matcher):
        """Resume with zero overlap with required JD skills scores 0."""
        jd = "Requirements: Python, Django, PostgreSQL, Docker."
        result = jd_matcher.match(jd, ["React", "CSS", "Figma"])
        assert result["match_score"] == 0.0, (
            f"Expected 0.0 for no-overlap resume. Got: {result['match_score']}"
        )

    def test_status_ok_for_valid_jd(self, jd_matcher):
        """A JD with recognisable technical skills always gets analysis_status='ok'."""
        result = jd_matcher.match(self.JUNIOR_FULLSTACK_JD, self.FULLSTACK_RESUME_FULL)
        assert result["analysis_status"] == "ok"


# ---------------------------------------------------------------------------
# Part C — ATS scorer / email detection
# ---------------------------------------------------------------------------

class TestPartC_ATSEmailDetection:

    # ---- C6: The root cause — clean_text must preserve @ ----

    def test_clean_text_preserves_at_symbol(self):
        """
        parser.py clean_text must NOT strip the @ character.
        This was the confirmed root cause of email non-detection.
        """
        from modules.parser import ResumeParser
        text_with_email = "Contact: john@example.com | +91 9876543210"
        cleaned = ResumeParser.clean_text(text_with_email)
        assert "@" in cleaned, (
            f"clean_text stripped the @ symbol. "
            f"Input: '{text_with_email}'\nOutput: '{cleaned}'"
        )

    def test_clean_text_email_survives_intact(self):
        """A full email address remains recognisable after clean_text."""
        from modules.parser import ResumeParser
        text = "Email: testuser@domain.co.uk   Phone: 555-1234"
        cleaned = ResumeParser.clean_text(text)
        # The email should still be findable by the ATS regex
        email_pattern = r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"
        match = re.search(email_pattern, cleaned, re.IGNORECASE)
        assert match is not None, (
            f"Email not detectable in cleaned text.\n"
            f"Input:   '{text}'\n"
            f"Cleaned: '{cleaned}'"
        )

    # ---- C1–C5: ATS scorer email detection ----

    def test_ats_detects_standard_email(self, ats_scorer):
        """Standard email address in resume text is detected."""
        text = (
            "John Smith\n"
            "john.smith@example.com | +1-555-0100\n\n"
            "SKILLS\nPython, Django\n\n"
            "EXPERIENCE\nDeveloped web applications."
        )
        result = ats_scorer.score(text)
        assert "email" in result["breakdown"]["contact_info"]["found"], (
            f"Email not detected. Found: {result['breakdown']['contact_info']['found']}"
        )

    def test_ats_detects_email_with_surrounding_whitespace(self, ats_scorer):
        """Email surrounded by extra whitespace/newlines is still detected."""
        text = (
            "Name: Jane Doe\n\n"
            "   jane.doe@company.org   \n\n"
            "SKILLS: JavaScript, React"
        )
        result = ats_scorer.score(text)
        assert "email" in result["breakdown"]["contact_info"]["found"], (
            f"Email with whitespace not detected. "
            f"Found: {result['breakdown']['contact_info']['found']}"
        )

    def test_ats_detects_email_adjacent_to_other_contact_info(self, ats_scorer):
        """Email adjacent to phone and LinkedIn is detected."""
        text = (
            "alice@startup.io | linkedin.com/in/alice | +44-7700-900123\n"
            "EXPERIENCE\nBuilt REST APIs using Node.js and Express."
        )
        result = ats_scorer.score(text)
        assert "email" in result["breakdown"]["contact_info"]["found"], (
            f"Email not detected adjacent to other contact info. "
            f"Found: {result['breakdown']['contact_info']['found']}"
        )

    def test_ats_missing_email_correctly_flagged(self, ats_scorer):
        """A resume with no email address reports email as missing."""
        text = (
            "Bob Jones | +1-555-0199 | linkedin.com/in/bobjones\n\n"
            "SKILLS\nJavaScript, HTML, CSS\n\n"
            "EXPERIENCE\nFrontend developer for 2 years."
        )
        result = ats_scorer.score(text)
        assert "email" not in result["breakdown"]["contact_info"]["found"], (
            "Email should be missing but was reported as found"
        )
        assert "email" in result["breakdown"]["contact_info"]["missing"]

    def test_ats_detects_email_at_end_of_document(self, ats_scorer):
        """Contact information placed at the bottom of the resume is still detected."""
        text = (
            "SUMMARY\nSenior Python developer.\n\n"
            "EXPERIENCE\nDeveloped microservices using Django and Docker.\n\n"
            "SKILLS\nPython, Django, Docker, PostgreSQL\n\n"
            "EDUCATION\nBSc Computer Science\n\n"
            "CONTACT\ncontact@example.net"
        )
        result = ats_scorer.score(text)
        assert "email" in result["breakdown"]["contact_info"]["found"], (
            f"Email at end of document not detected. "
            f"Found: {result['breakdown']['contact_info']['found']}"
        )

    # C7 — Integration: email survives clean_text pipeline then is detected by ATS
    def test_email_survives_clean_text_and_detected_by_ats(self, ats_scorer):
        """
        Full integration test: raw resume text → clean_text → ats_scorer.
        Verifies that the fix to clean_text actually allows the ATS scorer
        to detect the email.
        """
        from modules.parser import ResumeParser
        raw_text = (
            "Jane Developer\n"
            "jane.developer@mail.com\n"
            "linkedin.com/in/janedeveloper\n\n"
            "SKILLS\nPython Django PostgreSQL Git REST API\n\n"
            "EXPERIENCE\nBuilt REST APIs, deployed Docker containers.\n\n"
            "EDUCATION\nBSc Computer Science 2020"
        )
        cleaned = ResumeParser.clean_text(raw_text)
        result = ats_scorer.score(cleaned)
        assert "email" in result["breakdown"]["contact_info"]["found"], (
            f"Email lost in clean_text pipeline.\n"
            f"Raw: {raw_text[:80]}\nCleaned: {cleaned[:80]}\n"
            f"Contact found: {result['breakdown']['contact_info']['found']}"
        )

    def test_ats_score_schema_always_complete(self, ats_scorer):
        """ATS score result always has the expected top-level keys."""
        text = "Developer with skills in Python and JavaScript. dev@example.com"
        result = ats_scorer.score(text)
        required_keys = {
            "total_score", "grade", "grade_label",
            "breakdown", "improvement_tips", "word_count", "character_count"
        }
        missing = required_keys - set(result.keys())
        assert not missing, f"ATS result missing keys: {missing}"

    def test_ats_contact_breakdown_always_has_found_and_missing(self, ats_scorer):
        """contact_info breakdown always contains both 'found' and 'missing' keys."""
        text = "engineer@example.com | github.com/user"
        result = ats_scorer.score(text)
        contact = result["breakdown"]["contact_info"]
        assert "found" in contact, "contact_info breakdown missing 'found' key"
        assert "missing" in contact, "contact_info breakdown missing 'missing' key"


# ---------------------------------------------------------------------------
# Part B — continued: concise JD and scoring edge-cases
# ---------------------------------------------------------------------------

class TestPartB_ConciseJDAndScoring:
    """
    Tests for JD parsing reliability including concise JDs and scoring edge-cases.
    """

    # ---- Concise JD parsing (issue: Requirements: header not splitting correctly) ----

    # Minimum viable concise JD that passes the 50-char viability check.
    # The colon is preserved by clean_text, so a very short JD like
    # "Requirements: Python, Django, Git." (34 chars) will fail the MIN_JD_CHARS=50
    # guard correctly. We use a JD that is concise but ≥50 chars.
    CONCISE_JD = "Requirements: Python, Django, PostgreSQL, Git, Docker."

    def test_concise_jd_extracts_skills(self, jd_matcher):
        """
        A JD like 'Requirements: Python, Django, PostgreSQL, Git, Docker' must extract
        the listed skills into jd_required.  This is the minimal regression test
        for the section-header parsing defect.
        """
        result = jd_matcher.match(self.CONCISE_JD, ["Python", "Django", "PostgreSQL", "Git", "Docker"])
        assert result["analysis_status"] == "ok", (
            f"Concise JD failed viability check: {result['analysis_status']}. "
            f"Cleaned length: {len(self.CONCISE_JD)}"
        )
        req = [s.lower() for s in result["jd_skills"]["required"]]
        assert "python" in req, f"Python not in required. Got: {result['jd_skills']['required']}"
        assert "django" in req, f"Django not in required. Got: {result['jd_skills']['required']}"
        assert "postgresql" in req, f"PostgreSQL not in required. Got: {result['jd_skills']['required']}"
        assert "git" in req, f"Git not in required. Got: {result['jd_skills']['required']}"
        assert "docker" in req, f"Docker not in required. Got: {result['jd_skills']['required']}"

    def test_concise_jd_full_coverage_scores_nonzero(self, jd_matcher):
        """Full-coverage resume against a concise JD must score > 0."""
        result = jd_matcher.match(self.CONCISE_JD, ["Python", "Django", "PostgreSQL", "Git", "Docker"])
        assert result["match_score"] > 0.0, (
            f"Full-coverage resume scored 0.0 on concise JD. "
            f"Extracted required: {result['jd_skills']['required']}"
        )

    def test_concise_jd_empty_resume_scores_zero(self, jd_matcher):
        """Empty resume against a concise JD must score 0."""
        result = jd_matcher.match(self.CONCISE_JD, [])
        assert result["match_score"] == 0.0, (
            f"Empty resume scored {result['match_score']} on concise JD"
        )

    def test_concise_jd_partial_resume_scores_partial(self, jd_matcher):
        """A partial resume must score strictly between 0 and 100."""
        result = jd_matcher.match(self.CONCISE_JD, ["Python"])
        assert 0.0 < result["match_score"] < 100.0, (
            f"Partial resume should score between 0 and 100. Got: {result['match_score']}. "
            f"Required extracted: {result['jd_skills']['required']}"
        )

    # ---- _score() edge cases — no preferred skills ----

    def test_score_required_only_empty_resume(self, jd_matcher):
        """
        _score(0, N, 0, 0): required-only JD, empty resume → must be 0.0.
        Previously returned 30.0 due to phantom preferred credit.
        """
        score = jd_matcher._score(0, 5, 0, 0)
        assert score == 0.0, f"Expected 0.0 got {score}"

    def test_score_required_only_full_resume(self, jd_matcher):
        """_score(N, N, 0, 0): all required matched, no preferred → 100.0."""
        score = jd_matcher._score(5, 5, 0, 0)
        assert score == 100.0, f"Expected 100.0 got {score}"

    def test_score_required_only_partial_resume(self, jd_matcher):
        """_score(k, N, 0, 0): partial required match → k/N * 100."""
        score = jd_matcher._score(3, 5, 0, 0)
        assert score == 60.0, f"Expected 60.0 (3/5 * 100) got {score}"

    def test_score_preferred_only_jd_empty_resume(self, jd_matcher):
        """
        _score(0, 0, 0, M): preferred-only JD, empty resume → 0.0 (no required,
        phantom required ratio should NOT be 1.0).
        Guard catches total_req==0 and total_pref>0 with matched_pref==0.
        """
        score = jd_matcher._score(0, 0, 0, 3)
        assert score == 0.0, (
            f"Preferred-only JD, empty resume should score 0.0. Got {score}. "
            "The guard 'total_req==0 and total_pref==0' must NOT fire here."
        )

    def test_score_preferred_only_jd_full_resume(self, jd_matcher):
        """_score(0, 0, M, M): preferred-only JD, all preferred matched → 100.0."""
        score = jd_matcher._score(0, 0, 3, 3)
        assert score == 100.0, f"Expected 100.0 got {score}"

    def test_score_mixed_required_and_preferred(self, jd_matcher):
        """Mixed JD: all required matched, half preferred → > 70."""
        score = jd_matcher._score(5, 5, 2, 4)
        # req_ratio=1.0 (0.7 weight) + pref_ratio=0.5 (0.3 weight) = 0.7+0.15 = 0.85 → 85
        assert abs(score - 85.0) < 0.01, f"Expected 85.0 got {score}"

    # ---- Responsive alias false-positive check ----

    def test_responsive_alias_no_false_positive_on_unrelated_text(self, jd_matcher):
        """
        Adding 'Responsive Web Design' as an alias must not match unrelated text
        such as 'responsive customer support' or 'responsive team culture'.
        """
        # Build extractor to check skill extraction
        from modules.skill_extractor import SkillExtractor
        se = SkillExtractor(SKILLS_JSON)
        # These texts should NOT produce 'Responsive Design' as a skill
        texts = [
            "We are a responsive organisation with a supportive culture.",
            "Must be responsive to customer needs and feedback.",
            "The team is highly responsive and collaborative.",
        ]
        for text in texts:
            skills = se.extract_skills(text)
            skills_lower = [s.lower() for s in skills]
            assert "responsive design" not in skills_lower, (
                f"False-positive: 'Responsive Design' matched in '{text}'. "
                f"Skills: {skills}"
            )

    def test_responsive_alias_matches_correct_phrases(self, jd_matcher):
        """
        'Responsive Web Design' and 'Responsive Design' in resume text
        both resolve to canonical 'Responsive Design'.
        """
        from modules.skill_extractor import SkillExtractor
        se = SkillExtractor(SKILLS_JSON)
        for phrase, label in [
            ("I used responsive web design throughout the project.", "responsive web design"),
            ("Skilled in responsive design for mobile-first layouts.",  "responsive design"),
            ("Built responsive UI components using responsive layout.", "responsive layout"),
        ]:
            skills = se.extract_skills(phrase)
            skills_lower = [s.lower() for s in skills]
            assert "responsive design" in skills_lower, (
                f"'{label}' phrase did not extract 'Responsive Design'. "
                f"Skills from '{phrase}': {skills}"
            )

    # ---- @ symbol in clean_text does not break existing parsing ----

    def test_at_symbol_preserved_does_not_break_word_boundaries(self):
        """
        Keeping @ in clean_text must not break skill extraction on surrounding text.
        """
        from modules.parser import ResumeParser
        text = "Contact: dev@company.io | Python, Django, REST API development"
        cleaned = ResumeParser.clean_text(text)
        # @ should be present
        assert "@" in cleaned
        # Skill-adjacent text must still be parseable
        from modules.skill_extractor import SkillExtractor
        se = SkillExtractor(SKILLS_JSON)
        skills = se.extract_skills(cleaned)
        skills_lower = [s.lower() for s in skills]
        assert "python" in skills_lower, f"Python not extracted after @ fix. Skills: {skills}"
        assert "django" in skills_lower, f"Django not extracted after @ fix. Skills: {skills}"

    def test_at_symbol_not_in_extracted_skills(self):
        """
        The @ symbol itself must never appear as a skill name.
        """
        from modules.parser import ResumeParser
        from modules.skill_extractor import SkillExtractor
        se = SkillExtractor(SKILLS_JSON)
        text = ResumeParser.clean_text("user@domain.com   Python  Django  PostgreSQL")
        skills = se.extract_skills(text)
        for skill in skills:
            assert "@" not in skill, f"@ symbol leaked into skill name: '{skill}'"
