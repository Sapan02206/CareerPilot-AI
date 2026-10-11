"""
Skill Matcher Module - Industry Upgrade v3.0
Matches resume skills against job role requirements using:
1. Exact matching (fast, deterministic)
2. Fuzzy/alias matching (catches variations like "NodeJS" vs "Node.js")
3. Semantic similarity via difflib (no heavy ML dependency required)
"""

import json
import re
from difflib import SequenceMatcher
from typing import Dict, List, Tuple, Optional


def _fuzzy_similarity(a: str, b: str) -> float:
    """Return similarity ratio between two strings (0.0 to 1.0)."""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


class SkillMatcher:
    """
    Match resume skills against job requirements with semantic/fuzzy fallback.

    Matching pipeline per skill pair:
      1. Exact lowercase match          → score 1.0
      2. Known alias lookup             → score 1.0
      3. Substring containment          → score 0.85
      4. Fuzzy string similarity ≥ 0.80 → score proportional
    """

    # Minimum fuzzy similarity to count as a match
    FUZZY_THRESHOLD = 0.80

    # Hand-curated semantic aliases beyond what skills.json covers
    SEMANTIC_ALIASES: Dict[str, List[str]] = {
        "node.js": ["nodejs", "node js", "node", "server-side javascript"],
        "react": ["react.js", "reactjs", "react js"],
        "vue.js": ["vue", "vuejs", "vue js"],
        "angular": ["angularjs", "angular js"],
        "next.js": ["next", "nextjs", "next js"],
        "express.js": ["express", "expressjs"],
        "postgresql": ["postgres", "psql", "pg", "postgre"],
        "mongodb": ["mongo", "mongodb atlas"],
        "machine learning": ["ml", "supervised learning", "unsupervised learning"],
        "deep learning": ["dl", "neural networks", "neural network"],
        "natural language processing": ["nlp", "text processing", "text mining"],
        "computer vision": ["cv", "image recognition", "image processing"],
        "kubernetes": ["k8s", "k 8 s"],
        "docker": ["containerization", "containers", "container"],
        "ci/cd": ["continuous integration", "continuous deployment", "continuous delivery", "cicd", "ci cd"],
        "aws": ["amazon web services", "amazon aws", "amazon cloud"],
        "azure": ["microsoft azure", "ms azure", "azure cloud"],
        "google cloud": ["gcp", "google cloud platform", "google cloud services"],
        "linux": ["unix", "ubuntu", "centos", "debian", "rhel", "redhat", "fedora"],
        "rest api": ["restful", "restful api", "rest", "api development", "web api", "http api"],
        "graphql": ["gql", "graph ql"],
        "typescript": ["ts", "typed javascript"],
        "javascript": ["js", "ecmascript", "es6", "vanilla js", "es2015"],
        "python": ["python3", "python 3", "py"],
        "shell scripting": ["bash", "bash scripting", "shell script", "bash script", "sh script"],
        "terraform": ["infrastructure as code", "iac", "hashicorp terraform"],
        "git": ["version control", "github", "gitlab", "bitbucket"],
        "sql": ["structured query language", "relational database", "rdbms"],
        "agile": ["agile methodology", "agile development", "agile framework"],
        "scrum": ["scrum master", "scrum methodology"],
        "microservices": ["microservice", "microservice architecture", "soa"],
        "apache spark": ["spark", "pyspark", "apache spark"],
        "apache kafka": ["kafka", "event streaming"],
        "apache airflow": ["airflow", "workflow orchestration"],
        "llms": ["large language models", "large language model", "language models"],
        "prompt engineering": ["prompt design", "prompting"],
        "react native": ["rn", "react-native", "react native mobile"],
        "flutter": ["dart flutter", "flutter framework"],
        "swift": ["swift programming", "swiftui"],
        "kotlin": ["kotlin programming", "jetpack compose"],
        "penetration testing": ["pen testing", "pentest", "ethical hacking"],
        "solidity": ["ethereum smart contracts", "smart contract development"],
        "tailwind css": ["tailwind", "tailwindcss"],
        "bootstrap": ["bootstrap 5", "bootstrap 4", "bootstrap css"],
    }

    def __init__(
        self,
        job_roles_data_path: str,
        required_weight: float = 1.0,
        optional_weight: float = 0.5,
    ):
        with open(job_roles_data_path, "r", encoding="utf-8") as f:
            self.job_roles = json.load(f)

        self.required_weight = required_weight
        self.optional_weight = optional_weight

        # Build reverse alias lookup: alias → canonical
        self._alias_map: Dict[str, str] = {}
        for canonical, aliases in self.SEMANTIC_ALIASES.items():
            self._alias_map[canonical] = canonical
            for alias in aliases:
                self._alias_map[alias.lower()] = canonical

    # ------------------------------------------------------------------ #
    #  Public API                                                          #
    # ------------------------------------------------------------------ #

    def get_available_roles(self) -> List[str]:
        """Return sorted list of all available job roles."""
        return sorted(self.job_roles.keys())

    def get_roles_by_category(self) -> Dict[str, List[str]]:
        """Return roles grouped by category."""
        categories: Dict[str, List[str]] = {}
        for role_name, role_data in self.job_roles.items():
            cat = role_data.get("category", "Other")
            categories.setdefault(cat, []).append(role_name)
        return dict(sorted(categories.items()))

    def get_role_details(self, role_name: str) -> Dict:
        """Return full details for a specific role."""
        return self.job_roles.get(role_name, {})

    def match_skills(self, resume_skills: List[str], role_name: str) -> Dict:
        """
        Match resume skills against a job role using multi-tier matching.

        Returns a rich result dict with per-skill match details,
        fuzzy matches, and a weighted 0-100 score.
        """
        if role_name not in self.job_roles:
            available = ", ".join(sorted(self.job_roles.keys()))
            raise ValueError(
                f"Job role '{role_name}' not found. Available roles: {available}"
            )

        role_data = self.job_roles[role_name]
        required_skills = [s.lower() for s in role_data["required_skills"]]
        optional_skills = [s.lower() for s in role_data["optional_skills"]]

        # Normalise resume skills through alias map
        resume_skills_norm = [self._normalise(s) for s in resume_skills]

        # Match required skills
        req_matched, req_missing, req_fuzzy = self._match_skill_list(
            required_skills, resume_skills_norm
        )
        # Match optional skills
        opt_matched, opt_missing, opt_fuzzy = self._match_skill_list(
            optional_skills, resume_skills_norm
        )

        match_score = self._calculate_score(
            len(req_matched),
            len(required_skills),
            len(opt_matched),
            len(optional_skills),
        )

        # Collect fuzzy matches for transparency
        all_fuzzy = req_fuzzy + opt_fuzzy

        return {
            "role_name": role_name,
            "role_description": role_data["description"],
            "experience_level": role_data["experience_level"],
            "avg_salary": role_data.get("avg_salary", "N/A"),
            "category": role_data.get("category", "Other"),
            "match_score": round(match_score, 2),
            # Use original casing from role definition
            "matched_required": self._restore_case(req_matched, role_data["required_skills"]),
            "missing_required": self._restore_case(req_missing, role_data["required_skills"]),
            "matched_optional": self._restore_case(opt_matched, role_data["optional_skills"]),
            "missing_optional": self._restore_case(opt_missing, role_data["optional_skills"]),
            "fuzzy_matches": all_fuzzy,
            "total_resume_skills": len(resume_skills),
            "total_required_skills": len(required_skills),
            "total_optional_skills": len(optional_skills),
        }

    def compare_multiple_roles(self, resume_skills: List[str]) -> List[Dict]:
        """
        Compare resume against all available roles.

        Returns list sorted by match_score descending,
        with top-match flag on the first entry.
        """
        results = []
        for role_name in self.job_roles:
            try:
                result = self.match_skills(resume_skills, role_name)
                results.append(result)
            except ValueError:
                continue

        results.sort(key=lambda x: x["match_score"], reverse=True)

        if results:
            results[0]["top_match"] = True

        return results

    def get_top_matches(self, resume_skills: List[str], top_n: int = 5) -> List[Dict]:
        """Return only top N role matches."""
        return self.compare_multiple_roles(resume_skills)[:top_n]

    # ------------------------------------------------------------------ #
    #  Internal helpers                                                    #
    # ------------------------------------------------------------------ #

    def _normalise(self, skill: str) -> str:
        """Normalise a skill name through the alias map."""
        key = skill.lower().strip()
        return self._alias_map.get(key, key)

    def _match_skill_list(
        self,
        role_skills: List[str],        # already lowercased
        resume_skills_norm: List[str],  # normalised
    ) -> Tuple[List[str], List[str], List[Dict]]:
        """
        For each role skill decide: matched / missing (+ fuzzy detail).

        Returns:
            matched   – role skill names that were found
            missing   – role skill names not found
            fuzzy_log – list of {role_skill, resume_skill, score} for fuzzy hits
        """
        matched: List[str] = []
        missing: List[str] = []
        fuzzy_log: List[Dict] = []

        for role_skill in role_skills:
            role_norm = self._normalise(role_skill)

            # 1. Exact / alias match
            if role_norm in resume_skills_norm:
                matched.append(role_skill)
                continue

            # 2. Substring containment  (e.g. "postgresql" in "postgresql 14")
            found_substr = False
            for rs in resume_skills_norm:
                if role_norm in rs or rs in role_norm:
                    matched.append(role_skill)
                    found_substr = True
                    break
            if found_substr:
                continue

            # 3. Fuzzy similarity
            best_score = 0.0
            best_match = ""
            for rs in resume_skills_norm:
                sim = _fuzzy_similarity(role_norm, rs)
                if sim > best_score:
                    best_score = sim
                    best_match = rs

            if best_score >= self.FUZZY_THRESHOLD:
                matched.append(role_skill)
                fuzzy_log.append(
                    {
                        "role_skill": role_skill,
                        "resume_skill": best_match,
                        "similarity": round(best_score, 2),
                    }
                )
            else:
                missing.append(role_skill)

        return matched, missing, fuzzy_log

    def _calculate_score(
        self,
        matched_req: int,
        total_req: int,
        matched_opt: int,
        total_opt: int,
    ) -> float:
        """
        Weighted score: required skills count 2× as much as optional.
        Formula: ((req_ratio * req_w) + (opt_ratio * opt_w)) / total_w * 100
        """
        if total_req == 0 and total_opt == 0:
            return 0.0

        req_score = (matched_req / total_req) * self.required_weight if total_req else 0
        opt_score = (matched_opt / total_opt) * self.optional_weight if total_opt else 0

        total_weight = self.required_weight + self.optional_weight
        return ((req_score + opt_score) / total_weight) * 100

    @staticmethod
    def _restore_case(skill_keys: List[str], original_list: List[str]) -> List[str]:
        """Restore original casing for matched/missing skills from the role definition."""
        original_lower = {s.lower(): s for s in original_list}
        return sorted(
            original_lower.get(k.lower(), k.title()) for k in skill_keys
        )
