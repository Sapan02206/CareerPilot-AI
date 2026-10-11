"""
JD Matcher Module - Industry Upgrade v3.0
Parses any raw job description text and matches it against a candidate's resume skills.

Key capabilities:
  - Extracts required/preferred skills directly from JD text (no predefined role needed)
  - Detects seniority level, employment type, salary hints from JD prose
  - Scores resume against the specific JD (not a generic template)
  - Identifies keyword gaps that ATS systems would flag
  - Works purely on stdlib + skills.json — no external NLP dependency
"""

import json
import re
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _clean_text(text: str) -> str:
    """Normalise whitespace and remove markdown/HTML artefacts."""
    text = re.sub(r"<[^>]+>", " ", text)          # strip HTML tags
    text = re.sub(r"[•·▪◦‣⦾⦿]", " ", text)        # bullet chars
    text = re.sub(r"[\r\n\t]+", " ", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------

class JDMatcher:
    """
    Parse a raw job description and match it against resume skills.

    Usage:
        jd_matcher = JDMatcher('data/skills.json')
        result = jd_matcher.match(jd_text, resume_skills)
    """

    # Patterns that signal a skill is *required*
    REQUIRED_SIGNALS = [
        r"\brequired\b", r"\bmust have\b", r"\bmust-have\b",
        r"\bessential\b", r"\bmandatory\b", r"\bnecessary\b",
        r"\bminimum\b", r"\bqualifications?\b", r"\brequirements?\b",
        r"\bexpected\b", r"\bdemonstrated\b", r"\bproven\b",
    ]

    # Patterns that signal a skill is *preferred / nice-to-have*
    PREFERRED_SIGNALS = [
        r"\bpreferred\b", r"\bnice to have\b", r"\bnice-to-have\b",
        r"\bdesired\b", r"\bbonus\b", r"\badvantage\b", r"\bplus\b",
        r"\bideally\b", r"\bwould be great\b", r"\boptional\b",
        r"\bwelcome\b", r"\bbeneficial\b",
    ]

    # Seniority keywords
    SENIORITY_MAP = {
        "intern":       ["intern", "internship"],
        "entry":        ["entry level", "entry-level", "junior", "jr.", "fresher", "graduate", "new grad", "0-2 years"],
        "mid":          ["mid level", "mid-level", "mid-senior", "2-4 years", "3-5 years", "2+ years", "3+ years"],
        "senior":       ["senior", "sr.", "5+ years", "5-8 years", "lead", "staff"],
        "principal":    ["principal", "8+ years", "10+ years", "distinguished"],
        "manager":      ["manager", "director", "head of", "vp", "vice president"],
    }

    # Employment type hints
    EMPLOYMENT_TYPES = {
        "full_time":  ["full time", "full-time", "permanent"],
        "part_time":  ["part time", "part-time"],
        "contract":   ["contract", "contractor", "freelance", "consulting"],
        "remote":     ["remote", "work from home", "wfh", "fully remote"],
        "hybrid":     ["hybrid"],
        "on_site":    ["on-site", "onsite", "in-office", "in office"],
    }

    def __init__(self, skills_data_path: str):
        with open(skills_data_path, "r", encoding="utf-8") as f:
            self.skills_data = json.load(f)

        # Build flat skill list with original casing
        self.all_skills: List[str] = self._build_skill_list()

        # Build alias → canonical map
        self.alias_map: Dict[str, str] = self._build_alias_map()

        # Lowercase set for fast lookup
        self._skills_lower = {s.lower(): s for s in self.all_skills}

    # ------------------------------------------------------------------ #
    #  Public API                                                          #
    # ------------------------------------------------------------------ #

    # Minimum character length for a JD to be considered analysable after cleaning.
    MIN_JD_CHARS = 50

    def match(self, jd_text: str, resume_skills: List[str]) -> Dict:
        """
        Full JD analysis + resume match.

        Returns a structured result in all cases — including unanalysable JDs.
        The caller can inspect ``result["analysis_status"]`` to detect problems:

            "ok"                 — normal result, score is meaningful
            "jd_empty"           — jd_text was blank
            "jd_too_short"       — fewer than 50 characters after cleaning
            "no_skills_detected" — JD text contained no skills from the skill database
            "only_soft_skills"   — JD contained only general/soft-skill language

        For every non-"ok" status ``match_score`` is 0 (or 10 for soft-only)
        and the ``recommendations`` list explains the issue to the user.

        Args:
            jd_text:       Raw job description text (plain text or HTML)
            resume_skills: List of skills extracted from the candidate's resume

        Returns:
            Comprehensive match result dict (same top-level keys in all cases)
        """
        clean_jd = _clean_text(jd_text)

        # ── Pre-flight viability check ──────────────────────────────────────
        is_viable, status, user_message = self._check_jd_viability(clean_jd)
        if not is_viable:
            metadata = self._extract_metadata(clean_jd)
            return self._unanalysable_response(
                status, user_message, metadata, resume_skills
            )

        # ── Normal pipeline ─────────────────────────────────────────────────

        # Step 1 — extract metadata
        metadata = self._extract_metadata(clean_jd)

        # Step 2 — extract skills from JD
        jd_required, jd_preferred = self._extract_jd_skills(clean_jd)
        all_jd_skills = list(dict.fromkeys(jd_required + jd_preferred))

        # Soft-only check: all extracted skills are non-technical
        soft_skills_lower = {s.lower() for s in self.skills_data.get("soft_skills", [])}
        all_extracted_lower = {s.lower() for s in all_jd_skills}
        if all_extracted_lower and all_extracted_lower.issubset(soft_skills_lower):
            return self._unanalysable_response(
                "only_soft_skills",
                (
                    "Only general/soft skills were detected in this job description. "
                    "Add technical skill keywords (e.g. Python, React, AWS) for an "
                    "accurate match score."
                ),
                metadata,
                resume_skills,
                soft_score=10.0,
                jd_required=jd_required,
                jd_preferred=jd_preferred,
            )

        # Step 3 — match resume skills against JD skills
        resume_norm = [self._normalise(s) for s in resume_skills]

        matched_required, missing_required = self._compare(jd_required, resume_norm)
        matched_preferred, missing_preferred = self._compare(jd_preferred, resume_norm)

        # Step 4 — calculate score
        score = self._score(
            len(matched_required), len(jd_required),
            len(matched_preferred), len(jd_preferred),
        )

        # Step 5 — keyword gap
        keyword_gaps = self._rank_gaps(missing_required, missing_preferred, clean_jd)

        # Step 5b — surface JD requirements we could not map to any known skill
        unrecognised = self._extract_unrecognised_requirements(clean_jd, all_jd_skills)

        # Step 6 — tailored recommendations
        recommendations = self._generate_recommendations(
            missing_required, missing_preferred, score, metadata
        )

        return {
            "analysis_status": "ok",
            "match_score": round(score, 2),
            "metadata": metadata,
            "jd_skills": {
                "required": jd_required,
                "preferred": jd_preferred,
                "total": len(all_jd_skills),
            },
            "resume_match": {
                "matched_required": matched_required,
                "missing_required": missing_required,
                "matched_preferred": matched_preferred,
                "missing_preferred": missing_preferred,
                "total_resume_skills": len(resume_skills),
            },
            "keyword_gaps": keyword_gaps,
            "unrecognised_requirements": unrecognised,
            "scoring_note": (
                f"Score is calculated over {len(all_jd_skills)} recognised skill(s). "
                f"{len(unrecognised)} requirement(s) could not be mapped to the skill "
                "database and were excluded from scoring."
            ) if unrecognised else None,
            "recommendations": recommendations,
            "score_breakdown": {
                "required_coverage": round(
                    (len(matched_required) / len(jd_required) * 100) if jd_required else 100, 1
                ),
                "preferred_coverage": round(
                    (len(matched_preferred) / len(jd_preferred) * 100) if jd_preferred else 100, 1
                ),
            },
        }

    def extract_skills_from_jd(self, jd_text: str) -> Dict:
        """
        Lightweight extraction — just returns required/preferred skill lists.
        Useful for previewing what skills a JD demands.
        """
        clean_jd = _clean_text(jd_text)
        required, preferred = self._extract_jd_skills(clean_jd)
        return {"required": required, "preferred": preferred}

    # ------------------------------------------------------------------ #
    #  Viability helpers                                                   #
    # ------------------------------------------------------------------ #

    def _check_jd_viability(self, clean_jd: str) -> Tuple[bool, str, str]:
        """
        Decide whether a cleaned JD string is worth analysing.

        Returns:
            (is_viable, status_code, user_message)

        Status codes (non-viable only):
            "jd_empty"           — blank after cleaning (or whitespace-only)
            "jd_too_short"       — fewer than MIN_JD_CHARS characters after strip
            "no_skills_detected" — no *technical* skill from the database appears
                                   in the text (soft-skills-only text also lands here)
        """
        # Strip whitespace first so "   " is treated the same as ""
        stripped = clean_jd.strip()

        if not stripped:
            return False, "jd_empty", (
                "The job description was empty. Please paste the full text of the "
                "job posting to get an accurate match score."
            )

        if len(stripped) < self.MIN_JD_CHARS:
            return False, "jd_too_short", (
                f"The job description is too short ({len(stripped)} characters). "
                "Paste the complete job posting — including requirements, "
                "responsibilities, and qualifications — for a meaningful analysis."
            )

        # Check whether any known *technical* skill appears in the text.
        # Soft skills alone are not sufficient for meaningful matching, so a JD
        # that only mentions "communication" or "leadership" is treated the same
        # as one with no recognised skills at all.
        text_lower = stripped.lower()
        technical_skills = []
        for category_skills in self.skills_data.get("technical_skills", {}).values():
            technical_skills.extend(category_skills)

        found_technical = False
        for skill in technical_skills:
            pattern = r"\b" + re.escape(skill.lower()) + r"\b"
            if re.search(pattern, text_lower):
                found_technical = True
                break

        if not found_technical:
            return False, "no_skills_detected", (
                "No recognisable technical skills were found in this job description. "
                "This may happen if the posting uses unusual phrasing or proprietary "
                "tool names not in our database. Try pasting more of the job description, "
                "or check that the text was copied correctly."
            )

        return True, "ok", ""

    def _unanalysable_response(
        self,
        status: str,
        user_message: str,
        metadata: Dict,
        resume_skills: List[str],
        soft_score: float = 0.0,
        jd_required: Optional[List[str]] = None,
        jd_preferred: Optional[List[str]] = None,
    ) -> Dict:
        """
        Build a safe, complete response dict for an unanalysable JD.

        Always returns the same top-level keys as a normal ``match()`` result
        so the frontend never encounters a KeyError.
        """
        jd_required  = jd_required  or []
        jd_preferred = jd_preferred or []

        return {
            "analysis_status": status,
            "match_score": soft_score,
            "metadata": metadata,
            "jd_skills": {
                "required": jd_required,
                "preferred": jd_preferred,
                "total": len(jd_required) + len(jd_preferred),
            },
            "resume_match": {
                "matched_required": [],
                "missing_required": jd_required,
                "matched_preferred": [],
                "missing_preferred": jd_preferred,
                "total_resume_skills": len(resume_skills),
            },
            "keyword_gaps": [],
            "unrecognised_requirements": [],
            "scoring_note": None,
            "recommendations": [
                {
                    "priority": 1,
                    "type": "jd_analysis_error",
                    "title": "Job description could not be analysed",
                    "detail": user_message,
                }
            ],
            "score_breakdown": {
                "required_coverage": 0.0,
                "preferred_coverage": 0.0,
            },
        }

    # ------------------------------------------------------------------ #
    #  Metadata extraction                                                 #
    # ------------------------------------------------------------------ #

    def _extract_metadata(self, text: str) -> Dict:
        """Extract seniority, employment type, salary hints, remote info."""
        text_lower = text.lower()

        # Seniority
        seniority = "not specified"
        for level, keywords in self.SENIORITY_MAP.items():
            if any(kw in text_lower for kw in keywords):
                seniority = level
                break

        # Employment type (can be multiple)
        employment = []
        for etype, keywords in self.EMPLOYMENT_TYPES.items():
            if any(kw in text_lower for kw in keywords):
                employment.append(etype)

        # Salary extraction — broad pattern
        salary_hints = []
        salary_patterns = [
            r"\$[\d,]+(?:k|K)?(?:\s*[-–]\s*\$?[\d,]+(?:k|K)?)?",
            r"[\d,]+(?:k|K)?\s*(?:usd|USD|GBP|gbp|EUR|eur)?\s*(?:per year|\/yr|\/year|per annum|pa)",
            r"salary[\s:]+[\d,]+",
        ]
        for pat in salary_patterns:
            found = re.findall(pat, text)
            salary_hints.extend(found)

        # Years of experience
        exp_patterns = re.findall(
            r"(\d+)[\+\-]?\s*(?:to\s*\d+)?\s*years?\s+(?:of\s+)?experience", text_lower
        )
        years_required = int(exp_patterns[0]) if exp_patterns else None

        return {
            "seniority": seniority,
            "employment_type": employment if employment else ["not specified"],
            "salary_hints": salary_hints[:3],
            "years_experience_required": years_required,
        }

    # ------------------------------------------------------------------ #
    #  JD skill extraction                                                 #
    # ------------------------------------------------------------------ #

    def _extract_jd_skills(self, text: str) -> Tuple[List[str], List[str]]:
        """
        Two-pass extraction:
          Pass 1 — find section headers (Required, Preferred, etc.)
                   and classify skills found in those sections
          Pass 2 — scan remaining text for any known skills not yet classified

        Pass 1 fix: classified_positions now stores *absolute* character
        positions in the full text, preventing false collision when two
        different segments both have a skill at the same local offset
        (e.g. position 2 after ": ").

        Pass 2 fix: when both REQUIRED and PREFERRED signals appear in the
        ±200-char window, the signal *closer* to the skill wins, so a skill
        listed immediately after "Preferred:" is not promoted to required
        merely because "Requirements" appears earlier in the same window.
        """
        text_lower = text.lower()
        found_required: List[str] = []
        found_preferred: List[str] = []
        # Now stores ABSOLUTE positions in `text`, not segment-local offsets.
        classified_positions: set = set()

        # --- Pass 1: section-aware extraction ---
        section_pattern = re.compile(
            r"(requirements?|required\s+skills?|must.?have|qualifications?|"
            r"preferred|nice.?to.?have|desired|bonus|what\s+you.?ll\s+(?:need|bring)|"
            r"what\s+we.?re\s+looking\s+for|responsibilities?|about\s+you)",
            re.IGNORECASE,
        )
        segments = section_pattern.split(text)

        # Compute absolute start offset for each segment in the full text.
        # section_pattern.split() gives alternating [content, delimiter, content, …]
        segment_offsets: List[int] = []
        cursor = 0
        for seg in segments:
            segment_offsets.append(cursor)
            cursor += len(seg)

        current_section_type = "unknown"
        for i, segment in enumerate(segments):
            seg_lower = segment.lower().strip()
            seg_offset = segment_offsets[i]

            # Detect section type from header tokens
            if any(re.search(p, seg_lower) for p in self.REQUIRED_SIGNALS):
                current_section_type = "required"
            elif any(re.search(p, seg_lower) for p in self.PREFERRED_SIGNALS):
                current_section_type = "preferred"
            else:
                # Extract skills from this segment using absolute positions
                skills_in_seg = self._find_skills_in_text(segment)
                for skill, local_pos in skills_in_seg:
                    abs_pos = seg_offset + local_pos
                    if abs_pos not in classified_positions:
                        classified_positions.add(abs_pos)
                        if current_section_type == "required":
                            found_required.append(skill)
                        elif current_section_type == "preferred":
                            found_preferred.append(skill)

        # --- Pass 2: classify unclassified skills by proximity to signal words ---
        all_found_in_pass1 = set(s.lower() for s in found_required + found_preferred)

        for skill in self.all_skills:
            skill_lower = skill.lower()
            if skill_lower in all_found_in_pass1:
                continue

            pattern = r"\b" + re.escape(skill_lower) + r"\b"
            for m in re.finditer(pattern, text_lower):
                abs_pos = m.start()
                if abs_pos in classified_positions:
                    continue

                window_start = max(0, abs_pos - 200)
                window_end   = min(len(text_lower), m.end() + 200)
                window = text_lower[window_start:window_end]

                # Find the position of the nearest required/preferred signal
                # in the window so we can break ties by proximity.
                def _nearest_signal_dist(signals: List[str], win: str, skill_win_pos: int) -> int:
                    """Return distance from skill_win_pos to nearest signal match, or ∞."""
                    best = len(win) + 1
                    for p in signals:
                        for sm in re.finditer(p, win):
                            dist = abs(sm.start() - skill_win_pos)
                            if dist < best:
                                best = dist
                    return best

                skill_win_pos = abs_pos - window_start
                req_dist  = _nearest_signal_dist(self.REQUIRED_SIGNALS,  window, skill_win_pos)
                pref_dist = _nearest_signal_dist(self.PREFERRED_SIGNALS, window, skill_win_pos)

                is_required  = req_dist  <= len(window)
                is_preferred = pref_dist <= len(window)

                if is_required and is_preferred:
                    # Both signals present — the one *closer* to the skill wins
                    if pref_dist <= req_dist:
                        is_required = False
                    else:
                        is_preferred = False

                if is_required and skill not in found_required:
                    found_required.append(skill)
                    all_found_in_pass1.add(skill_lower)
                elif is_preferred and skill not in found_preferred:
                    found_preferred.append(skill)
                    all_found_in_pass1.add(skill_lower)
                elif not is_required and not is_preferred:
                    # No signal context — classify as required by default
                    if skill not in found_required:
                        found_required.append(skill)
                        all_found_in_pass1.add(skill_lower)
                break  # only process first occurrence per skill

        # Deduplicate while preserving order
        found_required = list(dict.fromkeys(found_required))
        found_preferred = list(dict.fromkeys(found_preferred))

        # Remove from preferred anything already in required
        req_set = set(s.lower() for s in found_required)
        found_preferred = [s for s in found_preferred if s.lower() not in req_set]

        return found_required, found_preferred

    def _find_skills_in_text(self, text: str) -> List[Tuple[str, int]]:
        """Find all known skills in a text segment. Returns (skill, position) tuples."""
        text_lower = text.lower()
        results = []
        for skill in self.all_skills:
            pattern = r"\b" + re.escape(skill.lower()) + r"\b"
            m = re.search(pattern, text_lower)
            if m:
                results.append((skill, m.start()))
        return results

    def _extract_unrecognised_requirements(
        self, clean_jd: str, recognised_skills: List[str]
    ) -> List[str]:
        """
        Find requirement-like phrases in the JD that contain no recognised skill.

        These are the items the scoring pipeline silently drops.  Surfacing them
        lets the caller warn the user that the score denominator is smaller than
        the full list of stated requirements.

        Strategy:
          1. Split the JD into short phrases by splitting on newlines, bullet
             chars, semicolons, and common list-item punctuation.
          2. Keep only phrases that look like requirements (contain a verb or
             skill-adjacent noun, or are preceded by a bullet/dash indicator).
          3. Drop any phrase that already contains at least one recognised skill.
          4. Drop fragments that are too short to be meaningful (< 4 words).

        Returns:
            List of short requirement strings not covered by the skill database.
            Capped at 20 entries to avoid noise.
        """
        # Build a lowercase set of recognised skills for fast containment check
        recognised_lower = {s.lower() for s in recognised_skills}

        # Split into candidate phrases
        # Treat newlines, common bullet markers, semicolons as delimiters
        raw_phrases = re.split(r'[\n\r;]|(?<!\w)-\s|\u2022|\u25aa|\u25cf|\*\s', clean_jd)

        unrecognised = []
        seen = set()

        for phrase in raw_phrases:
            phrase = phrase.strip()
            # Too short to be a meaningful requirement
            if len(phrase.split()) < 3:
                continue
            # Too long — likely a sentence paragraph, not a discrete requirement
            if len(phrase.split()) > 20:
                continue

            phrase_lower = phrase.lower()

            # Skip if it contains a recognised skill
            contains_skill = False
            for skill in recognised_lower:
                pattern = r"\b" + re.escape(skill) + r"\b"
                if re.search(pattern, phrase_lower):
                    contains_skill = True
                    break
            if contains_skill:
                continue

            # Skip near-duplicate phrases
            key = re.sub(r'\s+', ' ', phrase_lower).strip()
            if key in seen:
                continue
            seen.add(key)

            unrecognised.append(phrase)
            if len(unrecognised) >= 20:
                break

        return unrecognised

    # ------------------------------------------------------------------ #
    #  Matching & scoring                                                  #
    # ------------------------------------------------------------------ #

    def _normalise(self, skill: str) -> str:
        key = skill.lower().strip()
        return self.alias_map.get(key, key)

    def _compare(
        self, jd_skills: List[str], resume_norm: List[str]
    ) -> Tuple[List[str], List[str]]:
        """Split jd_skills into matched / missing against normalised resume skills."""
        matched, missing = [], []
        for skill in jd_skills:
            skill_norm = self._normalise(skill)
            found = False

            # Exact / alias
            if skill_norm in resume_norm:
                found = True
            else:
                # Substring
                for rs in resume_norm:
                    if skill_norm in rs or rs in skill_norm:
                        found = True
                        break
                # Fuzzy fallback
                if not found:
                    for rs in resume_norm:
                        if _similarity(skill_norm, rs) >= 0.82:
                            found = True
                            break

            (matched if found else missing).append(skill)
        return matched, missing

    def _score(
        self,
        matched_req: int, total_req: int,
        matched_pref: int, total_pref: int,
    ) -> float:
        """
        Score = required coverage (70%) + preferred coverage (30%).

        Component weights are adjusted based on which components exist in the JD:

        - Both required and preferred exist:   req*0.70 + pref*0.30
        - Required only (no preferred):        req*1.00
        - Preferred only (no required):        pref*1.00
        - Neither exists:                      0.0 (guard)

        This ensures an empty resume always scores 0 regardless of which
        components exist, and a full-coverage resume scores 100.
        """
        if total_req == 0 and total_pref == 0:
            return 0.0

        req_ratio  = (matched_req  / total_req)  if total_req  > 0 else None
        pref_ratio = (matched_pref / total_pref) if total_pref > 0 else None

        if req_ratio is not None and pref_ratio is not None:
            # Both components present — weighted combination
            return (req_ratio * 0.70 + pref_ratio * 0.30) * 100.0
        elif req_ratio is not None:
            # Required only — full weight on required coverage
            return req_ratio * 100.0
        else:
            # Preferred only — full weight on preferred coverage
            return pref_ratio * 100.0

    def _rank_gaps(
        self,
        missing_required: List[str],
        missing_preferred: List[str],
        jd_text: str,
    ) -> List[Dict]:
        """
        Rank missing skills by frequency in JD text — high-frequency = higher ATS impact.
        """
        gaps = []
        text_lower = jd_text.lower()
        for skill in missing_required:
            count = len(re.findall(r"\b" + re.escape(skill.lower()) + r"\b", text_lower))
            gaps.append({
                "skill": skill,
                "priority": "HIGH",
                "frequency_in_jd": max(count, 1),
                "impact": "Required — will likely be filtered by ATS",
            })
        for skill in missing_preferred:
            count = len(re.findall(r"\b" + re.escape(skill.lower()) + r"\b", text_lower))
            gaps.append({
                "skill": skill,
                "priority": "MEDIUM",
                "frequency_in_jd": count,
                "impact": "Preferred — adds competitive advantage",
            })

        # Sort: HIGH first, then by frequency descending
        gaps.sort(key=lambda x: (0 if x["priority"] == "HIGH" else 1, -x["frequency_in_jd"]))
        return gaps

    # ------------------------------------------------------------------ #
    #  Recommendations                                                     #
    # ------------------------------------------------------------------ #

    def _generate_recommendations(
        self,
        missing_required: List[str],
        missing_preferred: List[str],
        score: float,
        metadata: Dict,
    ) -> List[Dict]:
        recs = []

        if score >= 85:
            recs.append({
                "priority": 1,
                "type": "apply",
                "title": "Strong match — apply now",
                "detail": (
                    "Your skill profile closely matches this job description. "
                    "Tailor your resume summary to mirror the exact wording in the JD."
                ),
            })
        elif score >= 65:
            recs.append({
                "priority": 1,
                "type": "apply_with_gaps",
                "title": "Good match — apply while upskilling",
                "detail": (
                    "You meet most requirements. Apply now and address the "
                    f"{len(missing_required)} missing required skill(s) in parallel."
                ),
            })
        else:
            recs.append({
                "priority": 1,
                "type": "upskill_first",
                "title": "Upskill before applying",
                "detail": (
                    f"You're missing {len(missing_required)} required skill(s). "
                    "Spend 4–8 weeks closing the gap before submitting applications."
                ),
            })

        if missing_required:
            top_gaps = missing_required[:4]
            recs.append({
                "priority": 2,
                "type": "skill_gap",
                "title": f"Learn: {', '.join(top_gaps)}",
                "detail": (
                    "These required skills appear in the JD and are missing from your resume. "
                    "Focus here first — ATS systems will filter on these keywords."
                ),
            })

        if missing_preferred:
            recs.append({
                "priority": 3,
                "type": "bonus_skills",
                "title": f"Nice to have: {', '.join(missing_preferred[:3])}",
                "detail": (
                    "Adding these preferred skills will differentiate you from other candidates "
                    "with similar required skill coverage."
                ),
            })

        seniority = metadata.get("seniority", "not specified")
        years = metadata.get("years_experience_required")
        if years and years > 0:
            recs.append({
                "priority": 4,
                "type": "experience",
                "title": f"Experience required: {years}+ years ({seniority} level)",
                "detail": (
                    "Ensure your resume clearly quantifies years of experience per technology. "
                    "Phrases like '3 years of Python development' score better in ATS."
                ),
            })

        recs.append({
            "priority": 5,
            "type": "ats_tip",
            "title": "ATS optimisation tip",
            "detail": (
                "Use exact skill names from the JD in your resume — avoid synonyms. "
                "Include skills in a dedicated 'Skills' section AND in your experience bullets."
            ),
        })

        return recs

    # ------------------------------------------------------------------ #
    #  Data helpers                                                        #
    # ------------------------------------------------------------------ #

    def _build_skill_list(self) -> List[str]:
        skills = []
        for category_skills in self.skills_data.get("technical_skills", {}).values():
            skills.extend(category_skills)
        skills.extend(self.skills_data.get("soft_skills", []))
        # Deduplicate preserving order
        seen = set()
        result = []
        for s in skills:
            if s.lower() not in seen:
                seen.add(s.lower())
                result.append(s)
        return result

    def _build_alias_map(self) -> Dict[str, str]:
        alias_map: Dict[str, str] = {}
        for canonical, variants in self.skills_data.get("skill_variations", {}).items():
            alias_map[canonical.lower()] = canonical.lower()
            for v in variants:
                alias_map[v.lower()] = canonical.lower()
        return alias_map
