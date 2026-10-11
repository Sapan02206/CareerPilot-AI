"""
ATS Compatibility Scorer - Industry Upgrade v3.0

Simulates how an Applicant Tracking System evaluates a resume.
Real ATS systems (Workday, Greenhouse, Lever, iCIMS) score resumes on:
  1. Keyword density  — do required keywords appear enough times?
  2. Section presence — are standard sections (Experience, Skills, Education) present?
  3. Formatting       — are there formatting issues that break parsing?
  4. Contact info     — is basic contact information present?
  5. Quantification   — does the resume have measurable achievements?
  6. Action verbs     — do bullet points start with strong action verbs?
  7. File format      — was the file parseable (checked upstream)?

Score breakdown:
  Keyword Match       35%
  Section Structure   20%
  Contact Info        10%
  Quantification      15%
  Action Verbs        10%
  Formatting Quality  10%
"""

import re
from typing import Dict, List, Optional, Tuple


class ATSScorer:
    """
    Score a resume for ATS compatibility.

    Usage:
        scorer = ATSScorer()
        result = scorer.score(resume_text, required_keywords)
    """

    # Standard resume sections ATS expects
    EXPECTED_SECTIONS = {
        "experience":    [r"\bwork\s+experience\b", r"\bprofessional\s+experience\b",
                          r"\bemployment\s+history\b", r"\bexperience\b", r"\bwork\s+history\b"],
        "education":     [r"\beducation\b", r"\bacademic\s+background\b",
                          r"\bdegree\b", r"\bqualifications?\b"],
        "skills":        [r"\btechnical\s+skills\b", r"\bskills\b", r"\bcore\s+competencies\b",
                          r"\bproficiencies\b", r"\bexpertise\b"],
        "summary":       [r"\bprofessional\s+summary\b", r"\bsummary\b", r"\bprofile\b",
                          r"\bobjective\b", r"\babout\s+me\b"],
        "projects":      [r"\bprojects?\b", r"\bportfolio\b", r"\bkey\s+projects?\b"],
        "certifications":[r"\bcertifications?\b", r"\bcertified\b", r"\bcourses?\b",
                          r"\btraining\b", r"\bawards?\b"],
    }

    # Strong action verbs for bullet points
    ACTION_VERBS = [
        "developed", "designed", "built", "implemented", "created", "led",
        "managed", "delivered", "improved", "optimised", "optimized", "reduced",
        "increased", "launched", "architected", "engineered", "deployed",
        "automated", "integrated", "migrated", "scaled", "streamlined",
        "collaborated", "mentored", "established", "spearheaded", "drove",
        "accelerated", "transformed", "revamped", "maintained", "resolved",
        "analysed", "analyzed", "monitored", "configured", "coordinated",
        "contributed", "authored", "published", "presented", "trained",
    ]

    # Quantification patterns — numbers with context
    QUANTIFICATION_PATTERNS = [
        r"\d+\s*%",                                # percentages
        r"\$\s*\d+[kKmMbB]?",                     # money values
        r"\d+\s*(?:million|billion|thousand|k\b)", # large numbers
        r"\d+\s*(?:users?|customers?|clients?)",   # user counts
        r"\d+\s*(?:team\s+members?|engineers?|developers?)",  # team size
        r"(?:saved|reduced|increased|improved).*\d+",          # impact statements
        r"\d+x\s+(?:faster|improvement|increase|growth)",      # multipliers
        r"(?:from|by)\s+\d+\s*(?:to|%)",          # improvement ranges
    ]

    # Formatting red flags for ATS
    FORMAT_RED_FLAGS = [
        (r"[^\x00-\x7F]{3,}", "Non-ASCII characters detected — may break some parsers"),
        (r"\|{2,}", "Multiple pipe characters may indicate a table — ATS often misreads tables"),
        (r"_{5,}", "Long underscores may indicate a horizontal rule — often misread"),
        (r"\b(?:header|footer)\b", "Headers/footers may be dropped by ATS parsers"),
        (r"(?:Page\s+\d+\s+of\s+\d+)", "Page numbers can confuse parsers"),
    ]

    # Contact info patterns
    CONTACT_PATTERNS = {
        "email":   r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
        "phone":   r"(?:\+?\d[\d\s\-\(\)]{8,}\d)",
        "linkedin":r"linkedin\.com\/in\/[\w\-]+",
        "github":  r"github\.com\/[\w\-]+",
        "website": r"https?://[\w\-\.]+\.[a-z]{2,}",
    }

    def score(
        self,
        resume_text: str,
        required_keywords: Optional[List[str]] = None,
        job_title: Optional[str] = None,
    ) -> Dict:
        """
        Full ATS compatibility analysis.

        Args:
            resume_text:       Clean resume text
            required_keywords: List of skills/keywords from target role or JD
            job_title:         Optional target job title string

        Returns:
            Comprehensive ATS score report
        """
        required_keywords = required_keywords or []
        text_lower = resume_text.lower()

        # Run all checks
        keyword_result   = self._score_keywords(resume_text, required_keywords)
        section_result   = self._score_sections(text_lower)
        contact_result   = self._score_contact(resume_text)
        quant_result     = self._score_quantification(resume_text)
        action_result    = self._score_action_verbs(text_lower)
        format_result    = self._score_formatting(resume_text)

        # Weighted total
        total_score = (
            keyword_result["score"]   * 0.35 +
            section_result["score"]   * 0.20 +
            contact_result["score"]   * 0.10 +
            quant_result["score"]     * 0.15 +
            action_result["score"]    * 0.10 +
            format_result["score"]    * 0.10
        )

        # ATS grade
        grade, grade_label = self._grade(total_score)

        # Prioritised improvement tips
        tips = self._collect_tips(
            keyword_result, section_result, contact_result,
            quant_result, action_result, format_result
        )

        return {
            "total_score": round(total_score, 1),
            "grade": grade,
            "grade_label": grade_label,
            "breakdown": {
                "keyword_match": {
                    "score": keyword_result["score"],
                    "weight": "35%",
                    "matched_keywords": keyword_result["matched"],
                    "missing_keywords": keyword_result["missing"],
                    "keyword_density": keyword_result["density"],
                },
                "section_structure": {
                    "score": section_result["score"],
                    "weight": "20%",
                    "found_sections": section_result["found"],
                    "missing_sections": section_result["missing"],
                },
                "contact_info": {
                    "score": contact_result["score"],
                    "weight": "10%",
                    "found": contact_result["found"],
                    "missing": contact_result["missing"],
                },
                "quantification": {
                    "score": quant_result["score"],
                    "weight": "15%",
                    "count": quant_result["count"],
                    "examples": quant_result["examples"],
                },
                "action_verbs": {
                    "score": action_result["score"],
                    "weight": "10%",
                    "count": action_result["count"],
                    "found_verbs": action_result["found_verbs"],
                },
                "formatting": {
                    "score": format_result["score"],
                    "weight": "10%",
                    "issues": format_result["issues"],
                },
            },
            "improvement_tips": tips,
            "word_count": len(resume_text.split()),
            "character_count": len(resume_text),
        }

    # ------------------------------------------------------------------ #
    #  Individual scoring methods                                          #
    # ------------------------------------------------------------------ #

    def _score_keywords(self, text: str, keywords: List[str]) -> Dict:
        """Check how many required keywords appear in the resume."""
        if not keywords:
            return {"score": 100, "matched": [], "missing": [], "density": {}}

        text_lower = text.lower()
        matched, missing = [], []
        density = {}

        for kw in keywords:
            kw_lower = kw.lower()
            # Word-boundary match for multi-word skills too
            pattern = r"\b" + re.escape(kw_lower) + r"\b"
            count = len(re.findall(pattern, text_lower))
            if count > 0:
                matched.append(kw)
                density[kw] = count
            else:
                missing.append(kw)

        score = (len(matched) / len(keywords)) * 100 if keywords else 100
        return {"score": round(score, 1), "matched": matched, "missing": missing, "density": density}

    def _score_sections(self, text_lower: str) -> Dict:
        """Check for presence of standard resume sections."""
        found, missing = [], []

        for section, patterns in self.EXPECTED_SECTIONS.items():
            if any(re.search(p, text_lower) for p in patterns):
                found.append(section)
            else:
                missing.append(section)

        # Penalise missing critical sections more heavily
        critical = {"experience", "skills"}
        critical_missing = [s for s in missing if s in critical]
        non_critical_missing = [s for s in missing if s not in critical]

        base = (len(found) / len(self.EXPECTED_SECTIONS)) * 100
        penalty = len(critical_missing) * 15 + len(non_critical_missing) * 5
        score = max(0, base - penalty)

        return {"score": round(score, 1), "found": found, "missing": missing}

    def _score_contact(self, text: str) -> Dict:
        """Check for contact information presence."""
        found, missing = [], []

        for field, pattern in self.CONTACT_PATTERNS.items():
            if re.search(pattern, text, re.IGNORECASE):
                found.append(field)
            else:
                missing.append(field)

        # Email and phone are critical
        critical_found = sum(1 for f in ["email", "phone"] if f in found)
        score = (critical_found / 2) * 60 + (len(found) / len(self.CONTACT_PATTERNS)) * 40
        return {"score": round(min(score, 100), 1), "found": found, "missing": missing}

    def _score_quantification(self, text: str) -> Dict:
        """Check for measurable achievements and numbers."""
        examples = []
        for pattern in self.QUANTIFICATION_PATTERNS:
            matches = re.findall(pattern, text, re.IGNORECASE)
            examples.extend(matches[:2])  # keep a couple examples per pattern

        count = len(examples)
        examples = list(set(examples))[:5]  # deduplicate, keep top 5

        # 5+ quantified achievements = full score
        score = min((count / 5) * 100, 100)
        return {"score": round(score, 1), "count": count, "examples": examples}

    def _score_action_verbs(self, text_lower: str) -> Dict:
        """Check for strong action verbs at start of bullet points."""
        found_verbs = []
        for verb in self.ACTION_VERBS:
            if re.search(r"\b" + verb + r"\b", text_lower):
                found_verbs.append(verb)

        count = len(found_verbs)
        # 10+ distinct action verbs = full score
        score = min((count / 10) * 100, 100)
        return {"score": round(score, 1), "count": count, "found_verbs": found_verbs[:8]}

    def _score_formatting(self, text: str) -> Dict:
        """Detect formatting patterns that break ATS parsing."""
        issues = []
        for pattern, message in self.FORMAT_RED_FLAGS:
            if re.search(pattern, text):
                issues.append(message)

        # Word count check
        word_count = len(text.split())
        if word_count < 200:
            issues.append("Resume appears too short (< 200 words) — may lack keyword coverage")
        elif word_count > 1200:
            issues.append("Resume is very long (> 1200 words) — consider condensing to 1-2 pages")

        # Check for likely photo/image references (some ATS strip these)
        if re.search(r"\.(jpg|jpeg|png|gif|svg)\b", text, re.IGNORECASE):
            issues.append("Image file references detected — ATS systems typically cannot read images")

        score = max(0, 100 - len(issues) * 20)
        return {"score": round(score, 1), "issues": issues}

    # ------------------------------------------------------------------ #
    #  Grading & tips                                                      #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _grade(score: float) -> Tuple[str, str]:
        if score >= 85:
            return "A", "Excellent — highly ATS-friendly"
        elif score >= 70:
            return "B", "Good — minor improvements recommended"
        elif score >= 55:
            return "C", "Average — several issues to fix"
        elif score >= 40:
            return "D", "Poor — significant ATS barriers present"
        else:
            return "F", "Critical — resume likely filtered by ATS"

    def _collect_tips(self, *results) -> List[Dict]:
        """Aggregate actionable tips sorted by impact."""
        tips = []
        keyword_r, section_r, contact_r, quant_r, action_r, format_r = results

        if keyword_r["missing"]:
            tips.append({
                "priority": 1,
                "category": "Keywords",
                "impact": "HIGH",
                "tip": (
                    f"Add these missing keywords to your resume: "
                    f"{', '.join(keyword_r['missing'][:5])}. "
                    "Include them in your Skills section AND work experience bullets."
                ),
            })

        if section_r["missing"]:
            missing = [s.title() for s in section_r["missing"]]
            tips.append({
                "priority": 2,
                "category": "Sections",
                "impact": "HIGH" if any(s in ["experience", "skills"] for s in section_r["missing"]) else "MEDIUM",
                "tip": (
                    f"Add missing sections: {', '.join(missing)}. "
                    "ATS systems look for standard section headers to parse your resume correctly."
                ),
            })

        if quant_r["count"] < 3:
            tips.append({
                "priority": 3,
                "category": "Quantification",
                "impact": "HIGH",
                "tip": (
                    "Add measurable achievements. Replace vague statements like "
                    "'improved performance' with '35% faster response time by optimising database queries'. "
                    "Aim for 5+ quantified results."
                ),
            })

        if action_r["count"] < 6:
            tips.append({
                "priority": 4,
                "category": "Action Verbs",
                "impact": "MEDIUM",
                "tip": (
                    "Start bullet points with strong action verbs: "
                    "Developed, Built, Implemented, Optimised, Led, Deployed. "
                    "Avoid passive phrases like 'was responsible for'."
                ),
            })

        if "email" not in contact_r["found"]:
            tips.append({
                "priority": 1,
                "category": "Contact Info",
                "impact": "CRITICAL",
                "tip": "No email address detected. This will likely cause immediate rejection by ATS.",
            })

        if format_r["issues"]:
            for issue in format_r["issues"]:
                tips.append({
                    "priority": 3,
                    "category": "Formatting",
                    "impact": "MEDIUM",
                    "tip": issue,
                })

        if "linkedin" not in contact_r["found"]:
            tips.append({
                "priority": 5,
                "category": "Contact Info",
                "impact": "LOW",
                "tip": "Add your LinkedIn profile URL — many recruiters and ATS systems specifically look for it.",
            })

        if "github" not in contact_r["found"]:
            tips.append({
                "priority": 5,
                "category": "Contact Info",
                "impact": "LOW",
                "tip": "Add your GitHub profile URL — especially important for technical roles.",
            })

        # Sort by priority, then by impact weight
        impact_weight = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
        tips.sort(key=lambda t: (t["priority"], impact_weight.get(t["impact"], 4)))
        return tips
