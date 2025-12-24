#!/usr/bin/env python3
"""
SEO Fix Recommendation Engine

Converts all analytical signals into clear, actionable SEO fixes ordered by impact and effort.
Answers: "What should I fix first, on which page, and why?"

This module NEVER re-calculates. It only interprets existing signals.
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from collections import defaultdict


# Hard-coded effort rules
EFFORT_RULES = {
    "canonical": "LOW",
    "internal_links": "LOW",
    "redirect": "MEDIUM",
    "content_rewrite": "HIGH",
    "robots": "LOW",
    "noindex": "LOW",
    "structure": "MEDIUM",
    "consolidate": "HIGH"
}

# Time estimates per effort level (minutes)
TIME_ESTIMATES = {
    "LOW": 5,
    "MEDIUM": 15,
    "HIGH": 60
}


class SEOFixRecommendationEngine:
    """
    SEO Fix Recommendation Engine - Converts analysis into actionable fixes.
    
    Consumes outputs from:
    - Page Priority Engine
    - Canonical Clusters
    - Indexability Analyzer
    - Content Quality Analyzer
    - Link Graph
    - Redirect Resolver (optional)
    """
    
    def __init__(self, base_path: str):
        """
        Initialize SEO Fix Recommendation Engine.
        
        Args:
            base_path: Base path to input files
        """
        self.base_path = base_path
        self.base_name = Path(base_path).stem
        self.output_dir = Path(base_path).parent
        
        # Data storage
        self.priority_data = {}
        self.canonical_data = {}
        self.indexability_issues = []
        self.quality_data = {}
        self.link_graph_data = {}
        self.redirect_map = {}
        
        # Results
        self.fix_recommendations = []
    
    def load_inputs(self):
        """Load all required and optional input files."""
        print("Loading input files...\n")
        
        # Required: page_priority_scores.json
        priority_file = f"{self.base_path}_page_priority_scores.json"
        print(f"  ✓ Loading {Path(priority_file).name} (REQUIRED)...")
        try:
            with open(priority_file, 'r', encoding='utf-8') as f:
                priority_pages = json.load(f)
                self.priority_data = {p['url']: p for p in priority_pages}
            print(f"    Loaded {len(self.priority_data)} priority records")
        except FileNotFoundError:
            print(f"    ✗ Error: {Path(priority_file).name} not found")
            print(f"    Please run page_priority_engine.py first")
            raise
        
        # Required: pages_canonical_clusters.json
        canonical_file = f"{self.base_path}_pages_canonical_clusters.json"
        print(f"  ✓ Loading {Path(canonical_file).name} (REQUIRED)...")
        try:
            with open(canonical_file, 'r', encoding='utf-8') as f:
                canonical_data = json.load(f)
                # Handle both formats: direct list or wrapped in 'clusters'
                canonical_clusters = canonical_data.get('clusters', canonical_data) if isinstance(canonical_data, dict) else canonical_data
                
                # Build URL lookup
                for cluster in canonical_clusters:
                    leader = cluster.get('canonical_leader')
                    members = cluster.get('members', [])
                    
                    # Handle both member formats: dict with 'url' or string
                    for member in members:
                        member_url = member.get('url') if isinstance(member, dict) else member
                        self.canonical_data[member_url] = {
                            'canonical_leader': leader,
                            'cluster_size': len(members),
                            'is_leader': (member_url == leader)
                        }
            print(f"    Loaded {len(self.canonical_data)} canonical records")
        except FileNotFoundError:
            print(f"    ✗ Error: {Path(canonical_file).name} not found")
            print(f"    Please run canonical_clusters.py first")
            raise
        
        # Required: indexability_issues.json
        indexability_file = f"{self.base_path}_indexability_issues.json"
        print(f"  ✓ Loading {Path(indexability_file).name} (REQUIRED)...")
        try:
            with open(indexability_file, 'r', encoding='utf-8') as f:
                self.indexability_issues = json.load(f)
            print(f"    Loaded {len(self.indexability_issues)} indexability issues")
        except FileNotFoundError:
            print(f"    ✗ Error: {Path(indexability_file).name} not found")
            print(f"    Please run indexability_analyzer.py first")
            raise
        
        # Required: content_quality_pages.json
        quality_file = f"{self.base_path}_content_quality_pages.json"
        print(f"  ✓ Loading {Path(quality_file).name} (REQUIRED)...")
        try:
            with open(quality_file, 'r', encoding='utf-8') as f:
                quality_pages = json.load(f)
                self.quality_data = {p['url']: p for p in quality_pages}
            print(f"    Loaded {len(self.quality_data)} quality records")
        except FileNotFoundError:
            print(f"    ✗ Error: {Path(quality_file).name} not found")
            print(f"    Please run content_quality_analyzer.py first")
            raise
        
        # Required: pages_link_graph.json
        link_graph_file = f"{self.base_path}_pages_link_graph.json"
        print(f"  ✓ Loading {Path(link_graph_file).name} (REQUIRED)...")
        try:
            with open(link_graph_file, 'r', encoding='utf-8') as f:
                link_graph = json.load(f)
                self.link_graph_data = {node['url']: node for node in link_graph.get('nodes', [])}
            print(f"    Loaded {len(self.link_graph_data)} link graph nodes")
        except FileNotFoundError:
            print(f"    ✗ Error: {Path(link_graph_file).name} not found")
            print(f"    Please run link_graph.py first")
            raise
        
        # Optional: redirect_map.json
        redirect_file = f"{self.base_path}_pages_redirect_map.json"
        if os.path.exists(redirect_file):
            print(f"  ✓ Loading {Path(redirect_file).name} (OPTIONAL)...")
            with open(redirect_file, 'r', encoding='utf-8') as f:
                redirect_data = json.load(f)
                # Convert to simple URL -> final_url mapping
                self.redirect_map = {
                    url: data.get('final_url', url) 
                    for url, data in redirect_data.items()
                    if isinstance(data, dict)
                }
            print(f"    Loaded {len(self.redirect_map)} redirect mappings")
        else:
            print(f"  ⚠ {Path(redirect_file).name} not found (optional, skipping)")
        
        print("\nData loading complete.\n")
    
    def normalize_url(self, url: str) -> str:
        """
        Normalize URL using redirect_map → canonical.
        
        Args:
            url: URL to normalize
            
        Returns:
            Normalized URL
        """
        # Step 1: Resolve redirects
        final_url = self.redirect_map.get(url, url)
        
        # Step 2: Apply canonical
        canonical_info = self.canonical_data.get(final_url, {})
        canonical_url = canonical_info.get('canonical_leader', final_url)
        
        return canonical_url
    
    def detect_canonical_issues(self, url: str) -> List[Dict]:
        """Detect canonical-related issues with REFINEMENT 1: Severity tiers."""
        issues = []
        canonical_info = self.canonical_data.get(url, {})
        
        # Issue: Canonical redirect - REFINEMENT 1: Add severity tiers
        canonical_leader = canonical_info.get('canonical_leader')
        if canonical_leader and canonical_leader in self.redirect_map:
            # Check redirect chain depth
            redirect_target = self.redirect_map.get(canonical_leader)
            
            # Multi-hop redirect (HIGH severity)
            if redirect_target and redirect_target in self.redirect_map:
                issues.append({
                    "issue_code": "CANONICAL_REDIRECT",
                    "issue": "Canonical URL points to multi-hop redirect chain",
                    "fix": "Update canonical to final HTTPS resolved URL",
                    "effort": "LOW",
                    "source": "canonical_clusters",
                    "severity": "HIGH"  # REFINEMENT 1
                })
            # Single-hop redirect (LOW severity)
            else:
                issues.append({
                    "issue_code": "CANONICAL_REDIRECT",
                    "issue": "Canonical URL points to a single 301 redirect",
                    "fix": "Update canonical to final HTTPS resolved URL",
                    "effort": "LOW",
                    "source": "canonical_clusters",
                    "severity": "LOW"  # REFINEMENT 1
                })
        
        # Issue: Canonical missing (MEDIUM severity)
        if not canonical_info.get('is_leader', True) and not canonical_leader:
            issues.append({
                "issue_code": "CANONICAL_MISSING",
                "issue": "Page is not canonical leader but has no canonical tag",
                "fix": "Add self-canonical tag or point to cluster leader",
                "effort": "LOW",
                "source": "canonical_clusters",
                "severity": "MEDIUM"  # REFINEMENT 1
            })
        
        # Issue: Consolidate weak page in large cluster (HIGH severity if leader)
        cluster_size = canonical_info.get('cluster_size', 1)
        quality = self.quality_data.get(url, {})
        quality_grade = quality.get('quality_grade', 'C')
        is_leader = canonical_info.get('is_leader', False)
        
        if not is_leader and cluster_size > 1 and quality_grade in ['C', 'D']:
            issues.append({
                "issue_code": "CANONICAL_CONSOLIDATE",
                "issue": f"Weak page in cluster of {cluster_size} pages",
                "fix": "Consolidate content to cluster leader",
                "effort": "HIGH",
                "source": "canonical_clusters",
                "severity": "MEDIUM"  # REFINEMENT 1
            })
        
        return issues
    
    def detect_indexability_issues(self, url: str) -> List[Dict]:
        """Detect indexability-related issues."""
        issues = []
        
        # Find issues for this URL
        url_issues = [issue for issue in self.indexability_issues if issue.get('url') == url]
        
        for issue_data in url_issues:
            issue_type = issue_data.get('issue_type', '')
            
            if issue_type == 'noindex':
                quality = self.quality_data.get(url, {})
                page_intent = quality.get('page_intent', '')
                
                # Only flag if it's content page
                if page_intent in ['article', 'reference']:
                    issues.append({
                        "issue_code": "NOINDEX_CONTENT",
                        "issue": "Content page has noindex tag",
                        "fix": "Remove noindex tag to allow indexing",
                        "effort": "LOW",
                        "source": "indexability"
                    })
            
            elif issue_type == 'robots_blocked':
                issues.append({
                    "issue_code": "ROBOTS_BLOCKED",
                    "issue": "Page blocked by robots.txt",
                    "fix": "Allow crawling in robots.txt",
                    "effort": "LOW",
                    "source": "indexability"
                })
            
            elif issue_type == 'crawl_waste':
                issues.append({
                    "issue_code": "CRAWL_WASTE",
                    "issue": "Page wastes crawl budget",
                    "fix": "Reduce low-value pages or add noindex",
                    "effort": "MEDIUM",
                    "source": "indexability"
                })
        
        return issues
    
    def detect_content_quality_issues(self, url: str) -> List[Dict]:
        """Detect content quality-related issues."""
        issues = []
        quality = self.quality_data.get(url, {})
        
        if not quality:
            return issues
        
        quality_grade = quality.get('quality_grade', 'C')
        page_intent = quality.get('page_intent', '')
        recommended_action = quality.get('recommended_action', '')
        
        # Issue: Thin content
        if quality_grade == 'D' and page_intent == 'article':
            word_count = quality.get('word_count', 0)
            target = 800 if word_count < 400 else 1200
            issues.append({
                "issue_code": "THIN_CONTENT",
                "issue": f"Article has only {word_count} words (Grade D)",
                "fix": f"Expand content to {target}+ words",
                "effort": "HIGH",
                "source": "content_quality"
            })
        
        # Issue: Weak cluster leader
        canonical_info = self.canonical_data.get(url, {})
        if canonical_info.get('is_leader', False) and quality_grade in ['C', 'D']:
            cluster_size = canonical_info.get('cluster_size', 1)
            if cluster_size > 1:
                issues.append({
                    "issue_code": "WEAK_LEADER",
                    "issue": f"Cluster leader has low quality (Grade {quality_grade})",
                    "fix": "Strengthen content or merge cluster",
                    "effort": "HIGH",
                    "source": "content_quality"
                })
        
        # Issue: Poor structure
        heading_structure = quality.get('heading_structure', {})
        if not heading_structure.get('has_h1', True):
            issues.append({
                "issue_code": "POOR_STRUCTURE",
                "issue": "Page missing H1 heading",
                "fix": "Add H1 heading with target keyword",
                "effort": "LOW",
                "source": "content_quality"
            })
        
        # Issue: Recommended action is expand
        if recommended_action == 'expand':
            word_count = quality.get('word_count', 0)
            target = 800 if word_count < 400 else 1200
            issues.append({
                "issue_code": "CONTENT_EXPANSION",
                "issue": "Content needs expansion",
                "fix": f"Expand content to {target}+ words",
                "effort": "HIGH",
                "source": "content_quality"
            })
        
        return issues
    
    def detect_link_graph_issues(self, url: str) -> List[Dict]:
        """Detect link graph-related issues."""
        issues = []
        link_data = self.link_graph_data.get(url, {})
        
        if not link_data:
            return issues
        
        inlinks = link_data.get('inlinks', 0)
        outlinks = link_data.get('outlinks', 0)
        
        # Issue: Orphan page
        if inlinks == 0:
            issues.append({
                "issue_code": "ORPHAN_PAGE",
                "issue": "Page has no internal links pointing to it",
                "fix": "Add internal links from related pages",
                "effort": "LOW",
                "source": "link_graph"
            })
        
        # Issue: Weak authority
        elif inlinks < 3:
            issues.append({
                "issue_code": "WEAK_AUTHORITY",
                "issue": f"Page has only {inlinks} internal links",
                "fix": "Add 2-3 more internal links from hub pages",
                "effort": "LOW",
                "source": "link_graph"
            })
        
        # Issue: Dead-end page
        if outlinks == 0:
            issues.append({
                "issue_code": "DEAD_END",
                "issue": "Page has no outgoing links",
                "fix": "Add outgoing links to related content",
                "effort": "LOW",
                "source": "link_graph"
            })
        
        return issues
    
    def calculate_impact(self, priority_tier: str) -> str:
        """
        Calculate impact based on priority tier.
        
        Args:
            priority_tier: Priority tier
            
        Returns:
            Impact level (HIGH/MEDIUM/LOW)
        """
        if priority_tier == "CRITICAL":
            return "HIGH"
        elif priority_tier == "HIGH":
            return "MEDIUM"
        else:
            return "LOW"
    
    def calculate_fix_score(self, priority_tier: str, impact: str, effort: str) -> float:
        """
        Calculate fix priority score.
        
        Formula: (priority_weight * impact_weight * effort_weight) / 10
        
        Args:
            priority_tier: Priority tier
            impact: Impact level
            effort: Effort level
            
        Returns:
            Fix score
        """
        # Priority weight
        priority_weights = {
            "CRITICAL": 10,
            "HIGH": 7,
            "MEDIUM": 4,
            "LOW": 1,
            "IGNORE": 0
        }
        
        # Impact weight
        impact_weights = {
            "HIGH": 3,
            "MEDIUM": 2,
            "LOW": 1
        }
        
        # Effort weight (inverse - lower effort = higher score)
        effort_weights = {
            "LOW": 3,
            "MEDIUM": 2,
            "HIGH": 1
        }
        
        priority_weight = priority_weights.get(priority_tier, 1)
        impact_weight = impact_weights.get(impact, 1)
        effort_weight = effort_weights.get(effort, 1)
        
        # Formula ensures CRITICAL + LOW effort rises to top
        fix_score = (priority_weight * impact_weight * effort_weight) / 10
        
        return round(fix_score, 2)
    
    def calculate_confidence(self, fix_plan: List[Dict], url: str) -> float:
        """REFINEMENT 4: Cross-module confidence blending.
        
        Args:
            fix_plan: List of fixes
            url: Page URL
            
        Returns:
            Confidence score (0.0-1.0)
        """
        # REFINEMENT 4: Data completeness score
        data_completeness = 0.0
        
        # Check which data sources are available
        has_priority = url in self.priority_data
        has_canonical = url in self.canonical_data
        has_quality = url in self.quality_data
        has_link_graph = url in self.link_graph_data
        has_redirect_map = len(self.redirect_map) > 0
        
        # Each data source adds to completeness
        if has_priority: data_completeness += 0.2
        if has_canonical: data_completeness += 0.2
        if has_quality: data_completeness += 0.2
        if has_link_graph: data_completeness += 0.2
        if has_redirect_map: data_completeness += 0.2
        
        # REFINEMENT 4: Module agreement score
        module_agreement = 0.5  # Base
        
        # Check which data sources were used in fixes
        sources = set(fix.get('source', '') for fix in fix_plan)
        
        if 'canonical_clusters' in sources:
            module_agreement += 0.1
        if 'indexability' in sources:
            module_agreement += 0.1
        if 'content_quality' in sources:
            module_agreement += 0.1
        if 'link_graph' in sources:
            module_agreement += 0.1
        
        # Increase for multiple fixes (more signals)
        if len(fix_plan) >= 3:
            module_agreement += 0.1
        
        # REFINEMENT 4: Blend scores
        confidence = data_completeness * min(module_agreement, 1.0)
        
        # Penalize if link data is weak
        link_data = self.link_graph_data.get(url, {})
        if link_data.get('inlinks', 0) == 0:
            confidence *= 0.9  # Reduce confidence slightly
        
        return min(round(confidence, 2), 1.0)
    
    def should_skip_page(self, url: str) -> Tuple[bool, str]:
        """REFINEMENT 5: Do-nothing classification.
        
        Args:
            url: Page URL
            
        Returns:
            Tuple of (should_skip, reason)
        """
        quality = self.quality_data.get(url, {})
        page_intent = quality.get('page_intent', '')
        
        # Skip utility pages
        if page_intent in ['utility', 'index']:
            return True, "Utility/index page - thin by design"
        
        # Skip legal pages (heuristic: URL contains legal keywords)
        legal_keywords = ['/legal/', '/privacy/', '/terms/', '/cookie-policy/']
        if any(keyword in url.lower() for keyword in legal_keywords):
            return True, "Legal/privacy page - no optimization needed"
        
        # Skip if already optimal (A grade + no issues)
        quality_grade = quality.get('quality_grade', 'C')
        if quality_grade == 'A':
            return True, "Already optimal (Grade A)"
        
        return False, ""
    
    def estimate_time(self, fix_plan: List[Dict]) -> int:
        """
        Estimate time to complete all fixes.
        
        Args:
            fix_plan: List of fixes
            
        Returns:
            Estimated time in minutes
        """
        total_time = sum(TIME_ESTIMATES.get(fix.get('effort', 'MEDIUM'), 10) for fix in fix_plan)
        return total_time
    
    def analyze(self):
        """Run the complete fix recommendation analysis."""
        print("Analyzing SEO fixes...\n")
        
        for url in self.priority_data.keys():
            # Get priority data
            priority = self.priority_data.get(url, {})
            priority_tier = priority.get('priority_tier', 'LOW')
            
            # Skip IGNORE tier
            if priority_tier == 'IGNORE':
                continue
            
            # REFINEMENT 5: Check if page should be skipped
            should_skip, skip_reason = self.should_skip_page(url)
            if should_skip:
                # Add empty fix plan with reason
                recommendation = {
                    "url": url,
                    "priority_tier": priority_tier,
                    "fix_plan": [],
                    "estimated_time_minutes": 0,
                    "confidence": 1.0,
                    "skip_reason": skip_reason  # REFINEMENT 5
                }
                self.fix_recommendations.append(recommendation)
                continue
            
            # Detect all issues
            fix_plan = []
            
            # Canonical issues
            fix_plan.extend(self.detect_canonical_issues(url))
            
            # Indexability issues
            fix_plan.extend(self.detect_indexability_issues(url))
            
            # Content quality issues
            fix_plan.extend(self.detect_content_quality_issues(url))
            
            # Link graph issues
            fix_plan.extend(self.detect_link_graph_issues(url))
            
            # Calculate impact for each fix
            page_impact = self.calculate_impact(priority_tier)
            
            # REFINEMENT 3: Add fix-level priority and REFINEMENT 2: Quick win flag
            for fix in fix_plan:
                fix['impact'] = page_impact
                fix['fix_score'] = self.calculate_fix_score(
                    priority_tier, 
                    fix['impact'], 
                    fix['effort']
                )
                
                # REFINEMENT 3: Fix-level priority
                severity = fix.get('severity', 'MEDIUM')
                if severity == 'HIGH' or (fix['effort'] == 'LOW' and fix['impact'] in ['HIGH', 'MEDIUM']):
                    fix['fix_priority'] = 'HIGH'
                elif severity == 'MEDIUM' or fix['impact'] == 'MEDIUM':
                    fix['fix_priority'] = 'MEDIUM'
                else:
                    fix['fix_priority'] = 'LOW'
                
                # REFINEMENT 2: Quick win flag
                if fix['effort'] == 'LOW' and fix['impact'] in ['HIGH', 'MEDIUM']:
                    fix['quick_win'] = True
                else:
                    fix['quick_win'] = False
            
            # Sort fixes by fix_score (highest first)
            fix_plan.sort(key=lambda x: x.get('fix_score', 0), reverse=True)
            
            # Calculate metadata
            estimated_time = self.estimate_time(fix_plan)
            confidence = self.calculate_confidence(fix_plan, url)  # REFINEMENT 4: Pass URL
            
            # Build recommendation entry
            recommendation = {
                "url": url,
                "priority_tier": priority_tier,
                "fix_plan": fix_plan,
                "estimated_time_minutes": estimated_time,
                "confidence": confidence
            }
            
            self.fix_recommendations.append(recommendation)
        
        print(f"Analyzed {len(self.fix_recommendations)} pages\n")
    
    def export_results(self):
        """Export fix recommendations and summary."""
        print("Generating fix recommendation reports...\n")
        
        # Generate seo_fix_recommendations.json
        recommendations_file = self.output_dir / f"{self.base_name}_seo_fix_recommendations.json"
        with open(recommendations_file, 'w', encoding='utf-8') as f:
            json.dump(self.fix_recommendations, f, indent=2, ensure_ascii=False)
        print(f"  ✓ {recommendations_file.name}")
        
        # Generate summary
        total_pages = len(self.fix_recommendations)
        total_fixes = sum(len(rec['fix_plan']) for rec in self.fix_recommendations)
        
        fixes_by_type = defaultdict(int)
        fixes_by_effort = defaultdict(int)
        critical_fixes = 0
        quick_wins = 0
        total_time = 0
        
        for rec in self.fix_recommendations:
            if rec['priority_tier'] == 'CRITICAL':
                critical_fixes += len(rec['fix_plan'])
            
            total_time += rec['estimated_time_minutes']
            
            for fix in rec['fix_plan']:
                issue_code = fix['issue_code']
                effort = fix['effort']
                
                # Categorize by type
                if 'CANONICAL' in issue_code:
                    fixes_by_type['canonical'] += 1
                elif 'LINK' in issue_code or 'ORPHAN' in issue_code or 'AUTHORITY' in issue_code or 'DEAD_END' in issue_code:
                    fixes_by_type['internal_links'] += 1
                elif 'CONTENT' in issue_code or 'THIN' in issue_code or 'WEAK_LEADER' in issue_code or 'STRUCTURE' in issue_code:
                    fixes_by_type['content_quality'] += 1
                elif 'INDEX' in issue_code or 'ROBOTS' in issue_code or 'CRAWL' in issue_code:
                    fixes_by_type['indexability'] += 1
                
                # Count by effort
                fixes_by_effort[effort] += 1
                
                # REFINEMENT 2: Quick wins count
                if fix.get('quick_win', False):
                    quick_wins += 1
        
        summary = {
            "total_pages": total_pages,
            "total_fixes": total_fixes,
            "fixes_by_type": dict(sorted(fixes_by_type.items(), key=lambda x: x[1], reverse=True)),
            "fixes_by_effort": dict(fixes_by_effort),
            "critical_fixes": critical_fixes,
            "quick_wins": quick_wins,
            "total_estimated_hours": round(total_time / 60, 1)
        }
        
        summary_file = self.output_dir / f"{self.base_name}_seo_fix_summary.json"
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        print(f"  ✓ {summary_file.name}")
        
        print("\n" + "=" * 70)
        print("🚀 SEO FIX RECOMMENDATION ENGINE COMPLETE")
        print("=" * 70)
        print(f"\n  Total Pages: {total_pages}")
        print(f"  Total Fixes: {total_fixes}")
        print(f"\n  Fixes by Type:")
        for fix_type, count in list(summary['fixes_by_type'].items())[:5]:
            print(f"    {fix_type}: {count}")
        
        print(f"\n  Fixes by Effort:")
        for effort, count in summary['fixes_by_effort'].items():
            print(f"    {effort}: {count}")
        
        print(f"\n  Critical Fixes: {critical_fixes}")
        print(f"  Quick Wins: {quick_wins}")
        print(f"  Total Estimated Time: {summary['total_estimated_hours']} hours")
        
        print("\n" + "=" * 70 + "\n")
    
    def run(self):
        """Run the complete fix recommendation engine."""
        self.load_inputs()
        self.analyze()
        self.export_results()


def main():
    """Main entry point."""
    print("=" * 70)
    print("🚀 SEO FIX RECOMMENDATION ENGINE")
    print("=" * 70)
    print()
    
    # Get input path
    print("Enter path to your pages JSON file:")
    print("Example: crawler_output/developer_mozilla_org_20251220_054821_pages.json")
    print()
    pages_path = input("Pages JSON path: ").strip()
    
    if not pages_path:
        print("Error: No path provided")
        return
    
    # Remove _pages.json suffix if present
    if pages_path.endswith('_pages.json'):
        base_path = pages_path[:-len('_pages.json')]
    else:
        base_path = pages_path
    
    # Check if file exists
    if not os.path.exists(f"{base_path}_pages.json"):
        print(f"Error: File not found: {base_path}_pages.json")
        return
    
    print()
    print("=" * 70)
    print("🚀 SEO FIX RECOMMENDATION ENGINE")
    print("=" * 70)
    print()
    
    # Run analysis
    engine = SEOFixRecommendationEngine(base_path)
    engine.run()


if __name__ == "__main__":
    main()
