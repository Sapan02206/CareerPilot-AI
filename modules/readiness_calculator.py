"""
Readiness Calculator Module - Phase 2 MVP
Calculates career readiness score based on skills, experience, and evidence

VERSION: 1.0.0 (MVP)

FORMULA:
Readiness Score = (
    Skill Match Score × 0.50 +      # 50% - Do you have the skills?
    Experience Score × 0.30 +        # 30% - Do you have enough experience?
    Evidence Score × 0.20            # 20% - Can you prove it?
)
"""

from typing import Dict, List, Optional


class ReadinessCalculator:
    """Calculate career readiness scores and generate gap analysis"""
    
    def __init__(self):
        """Initialize calculator with weights"""
        self.skill_weight = 0.50
        self.experience_weight = 0.30
        self.evidence_weight = 0.20
    
    def calculate_readiness(self, enriched_skills: List[Dict], match_results: Dict, 
                          projects: List[Dict]) -> Dict:
        """
        Calculate overall readiness score
        
        Args:
            enriched_skills: Skills with experience data from skill_extractor
            match_results: Job matching results from matcher
            projects: List of user projects
            
        Returns:
            Dictionary with readiness scores and breakdown
        """
        # Calculate individual components
        skill_match_score = self.calculate_skill_match_score(match_results)
        experience_score = self.calculate_experience_score(
            enriched_skills, 
            match_results['matched_required'] + match_results['missing_required']
        )
        evidence_score = self.calculate_evidence_score(
            projects,
            match_results['matched_required'] + match_results['missing_required']
        )
        
        # Calculate weighted overall score
        overall_score = (
            skill_match_score * self.skill_weight +
            experience_score * self.experience_weight +
            evidence_score * self.evidence_weight
        )
        
        # Generate gap analysis
        gap_analysis = self.generate_gap_analysis(match_results, enriched_skills)
        
        # Generate basic recommendations
        recommendations = self.generate_basic_recommendations(gap_analysis, evidence_score)
        
        return {
            'overall_score': round(overall_score, 2),
            'skill_match_score': round(skill_match_score, 2),
            'experience_score': round(experience_score, 2),
            'evidence_score': round(evidence_score, 2),
            'gap_analysis': gap_analysis,
            'recommendations': recommendations,
            'breakdown': {
                'skill_match': {
                    'score': round(skill_match_score, 2),
                    'weight': self.skill_weight,
                    'contribution': round(skill_match_score * self.skill_weight, 2)
                },
                'experience': {
                    'score': round(experience_score, 2),
                    'weight': self.experience_weight,
                    'contribution': round(experience_score * self.experience_weight, 2)
                },
                'evidence': {
                    'score': round(evidence_score, 2),
                    'weight': self.evidence_weight,
                    'contribution': round(evidence_score * self.evidence_weight, 2)
                }
            }
        }
    
    def calculate_skill_match_score(self, match_results: Dict) -> float:
        """
        Calculate skill match component (0-100)
        
        Uses existing match_score from matcher.py which already considers
        required (70%) and optional (30%) skills
        
        Args:
            match_results: Results from SkillMatcher.match_skills()
            
        Returns:
            Skill match score (0-100)
        """
        return match_results.get('match_score', 0)
    
    def calculate_experience_score(self, enriched_skills: List[Dict], 
                                   required_skills: List[str]) -> float:
        """
        Calculate experience component (0-100)
        
        Based on average years of experience across required skills
        
        Scoring:
        - 0-1 years: 20 points (Beginner)
        - 1-2 years: 40 points (Junior)
        - 2-4 years: 60 points (Intermediate)
        - 4-7 years: 80 points (Advanced)
        - 7+ years: 100 points (Expert)
        
        Args:
            enriched_skills: Skills with experience data
            required_skills: List of required skill names
            
        Returns:
            Experience score (0-100)
        """
        if not required_skills:
            return 0
        
        # Build skill lookup
        skill_lookup = {s['skill'].lower(): s for s in enriched_skills}
        
        total_years = 0
        count = 0
        
        for skill in required_skills:
            skill_lower = skill.lower()
            if skill_lower in skill_lookup:
                skill_data = skill_lookup[skill_lower]
                if skill_data.get('experience_years'):
                    total_years += skill_data['experience_years']
                    count += 1
        
        if count == 0:
            return 0
        
        avg_years = total_years / count
        
        # Map years to score
        if avg_years >= 7:
            return 100
        elif avg_years >= 4:
            return 80
        elif avg_years >= 2:
            return 60
        elif avg_years >= 1:
            return 40
        else:
            return 20
    
    def calculate_evidence_score(self, projects: List[Dict], 
                                 required_skills: List[str]) -> float:
        """
        Calculate evidence component (0-100)
        
        Based on number of projects demonstrating required skills
        
        Scoring:
        - 0 projects: 0 points
        - 1 project: 25 points
        - 2 projects: 50 points
        - 3 projects: 75 points
        - 4+ projects: 100 points
        
        Bonus: +10 points per project with URL (verifiable), max +20
        
        Args:
            projects: List of user projects
            required_skills: List of required skill names
            
        Returns:
            Evidence score (0-100)
        """
        if not projects:
            return 0
        
        required_skills_lower = set(s.lower() for s in required_skills)
        relevant_projects = []
        
        for project in projects:
            # Check if project uses any required skills
            project_skills = project.get('skills_used', [])
            project_skills_lower = set(s.lower() for s in project_skills)
            
            if project_skills_lower.intersection(required_skills_lower):
                relevant_projects.append(project)
        
        # Base score
        project_count = len(relevant_projects)
        base_score = min(project_count * 25, 100)
        
        # Bonus for verifiable projects (has URL)
        verifiable_count = sum(1 for p in relevant_projects if p.get('project_url'))
        bonus = min(verifiable_count * 10, 20)
        
        return min(base_score + bonus, 100)
    
    def generate_gap_analysis(self, match_results: Dict, 
                             enriched_skills: List[Dict]) -> Dict:
        """
        Generate detailed gap analysis
        
        Args:
            match_results: Results from SkillMatcher
            enriched_skills: Skills with experience data
            
        Returns:
            Dictionary with gap analysis
        """
        # Build skill lookup
        skill_lookup = {s['skill'].lower(): s for s in enriched_skills}
        
        # Analyze matched required skills
        matched_required_details = []
        for skill in match_results['matched_required']:
            skill_lower = skill.lower()
            skill_data = skill_lookup.get(skill_lower, {})
            matched_required_details.append({
                'skill': skill,
                'experience_years': skill_data.get('experience_years'),
                'experience_confidence': skill_data.get('experience_confidence'),
                'experience_source': skill_data.get('experience_source')
            })
        
        # Analyze missing required skills
        missing_required_details = []
        for skill in match_results['missing_required']:
            missing_required_details.append({
                'skill': skill,
                'priority': 'HIGH',
                'reason': 'Required skill - Learn this first!'
            })
        
        # Analyze optional skills
        matched_optional_details = []
        for skill in match_results['matched_optional']:
            skill_lower = skill.lower()
            skill_data = skill_lookup.get(skill_lower, {})
            matched_optional_details.append({
                'skill': skill,
                'experience_years': skill_data.get('experience_years')
            })
        
        missing_optional_details = []
        for skill in match_results['missing_optional']:
            missing_optional_details.append({
                'skill': skill,
                'priority': 'MEDIUM',
                'reason': 'Optional skill - Nice to have'
            })
        
        return {
            'matched_required': matched_required_details,
            'missing_required': missing_required_details,
            'matched_optional': matched_optional_details,
            'missing_optional': missing_optional_details,
            'summary': {
                'total_required': len(match_results['matched_required']) + len(match_results['missing_required']),
                'matched_required_count': len(match_results['matched_required']),
                'missing_required_count': len(match_results['missing_required']),
                'total_optional': len(match_results['matched_optional']) + len(match_results['missing_optional']),
                'matched_optional_count': len(match_results['matched_optional']),
                'missing_optional_count': len(match_results['missing_optional'])
            }
        }
    
    def generate_basic_recommendations(self, gap_analysis: Dict, 
                                      evidence_score: float) -> List[Dict]:
        """
        Generate simple learning recommendations
        
        Args:
            gap_analysis: Gap analysis from generate_gap_analysis()
            evidence_score: Current evidence score
            
        Returns:
            List of recommendations
        """
        recommendations = []
        
        # Priority 1: Missing required skills
        if gap_analysis['missing_required']:
            for skill_data in gap_analysis['missing_required'][:3]:  # Top 3
                recommendations.append({
                    'priority': 1,
                    'type': 'skill_gap',
                    'title': f"Learn {skill_data['skill']}",
                    'detail': f"{skill_data['skill']} is a required skill for this role. Focus on this first.",
                    'estimated_time': '2-3 months',
                    'action': f"Complete a {skill_data['skill']} course and build a project"
                })
        
        # Priority 2: Add evidence if score is low
        if evidence_score < 50:
            recommendations.append({
                'priority': 2,
                'type': 'evidence',
                'title': 'Add Projects to Your Portfolio',
                'detail': f"Your evidence score is {evidence_score}/100. Add projects demonstrating your skills.",
                'estimated_time': '1-2 weeks per project',
                'action': 'Build 2-3 projects using the required skills'
            })
        
        # Priority 3: Optional skills (if required are covered)
        if not gap_analysis['missing_required'] and gap_analysis['missing_optional']:
            for skill_data in gap_analysis['missing_optional'][:2]:  # Top 2
                recommendations.append({
                    'priority': 3,
                    'type': 'skill_enhancement',
                    'title': f"Learn {skill_data['skill']} (Optional)",
                    'detail': f"{skill_data['skill']} is an optional skill that will boost your competitiveness.",
                    'estimated_time': '1-2 months',
                    'action': f"Learn {skill_data['skill']} basics and add to a project"
                })
        
        return recommendations[:5]  # Return top 5 recommendations
