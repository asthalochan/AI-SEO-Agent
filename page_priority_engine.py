#!/usr/bin/env python3
"""
Page Priority Engine (PPE)

Ranks pages by SEO impact opportunity to answer:
"If I can fix only 10 pages this month, which ones give me the biggest ROI?"

Priority ≠ Quality. High-quality blocked pages are CRITICAL.
Low-quality low-authority pages are LOW.
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from collections import defaultdict
from urllib.parse import urlparse


class PagePriorityEngine:
    """
    Page Priority Engine - Ranks pages by SEO impact opportunity.
    
    Consumes outputs from:
    - Crawler (pages.json)
    - Content Quality Analyzer
    - Indexability Analyzer
    - Link Graph
    - Canonical Clusters
    """
    
    def __init__(self, base_path: str):
        """
        Initialize Page Priority Engine.
        
        Args:
            base_path: Base path to input files (e.g., crawler_output/developer_mozilla_org_20251222_031422)
        """
        self.base_path = base_path
        self.base_name = Path(base_path).stem
        self.output_dir = Path(base_path).parent
        
        # Data storage
        self.pages = []
        self.quality_data = {}
        self.indexability_data = {}
        self.link_graph_data = {}
        self.canonical_data = {}
        self.redirect_map = {}
        
        # Results
        self.priority_scores = []
    
    def load_data(self):
        """Load all required and optional input files."""
        print("Loading input files...\n")
        
        # Required: pages.json
        pages_file = f"{self.base_path}_pages.json"
        print(f"  ✓ Loading {Path(pages_file).name} (REQUIRED)...")
        try:
            with open(pages_file, 'r', encoding='utf-8') as f:
                self.pages = json.load(f)
            print(f"    Loaded {len(self.pages)} pages")
        except FileNotFoundError:
            print(f"    ✗ Error: {Path(pages_file).name} not found")
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
        
        # Required: indexability_pages.json
        indexability_file = f"{self.base_path}_indexability_pages.json"
        print(f"  ✓ Loading {Path(indexability_file).name} (REQUIRED)...")
        try:
            with open(indexability_file, 'r', encoding='utf-8') as f:
                indexability_pages = json.load(f)
                self.indexability_data = {p['url']: p for p in indexability_pages}
            print(f"    Loaded {len(self.indexability_data)} indexability records")
        except FileNotFoundError:
            print(f"    ✗ Error: {Path(indexability_file).name} not found")
            print(f"    Please run indexability_analyzer.py first")
            raise
        
        # Required: link_graph.json
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
        
        # Required: canonical_clusters_page_index.json
        canonical_file = f"{self.base_path}_pages_canonical_clusters_page_index.json"
        print(f"  ✓ Loading {Path(canonical_file).name} (REQUIRED)...")
        try:
            with open(canonical_file, 'r', encoding='utf-8') as f:
                self.canonical_data = json.load(f)
            print(f"    Loaded {len(self.canonical_data)} canonical records")
        except FileNotFoundError:
            print(f"    ✗ Error: {Path(canonical_file).name} not found")
            print(f"    Please run canonical_clusters.py first")
            raise
        
        # Optional: redirect_map.json
        redirect_file = f"{self.base_path}_pages_redirect_map.json"
        if os.path.exists(redirect_file):
            print(f"  ✓ Loading {Path(redirect_file).name} (OPTIONAL)...")
            with open(redirect_file, 'r', encoding='utf-8') as f:
                self.redirect_map = json.load(f)
            print(f"    Loaded {len(self.redirect_map)} redirect mappings")
        else:
            print(f"  ⚠ {Path(redirect_file).name} not found (optional, skipping)")
        
        print("\nData loading complete.\n")
    
    def should_auto_demote(self, page: Dict, quality: Dict, indexability: Dict) -> bool:
        """
        Check if page should be auto-demoted to IGNORE tier.
        
        Pages that should never appear as CRITICAL:
        - noindex + utility
        - legal/privacy
        - redirect-only URLs
        - pagination
        - search result pages
        
        Args:
            page: Page data
            quality: Quality data
            indexability: Indexability data
            
        Returns:
            True if should be auto-demoted
        """
        url_lower = page['url'].lower()
        
        # Noindex utility pages
        if indexability.get('indexable') == False and quality.get('page_intent') == 'utility':
            return True
        
        # Legal/privacy pages
        if any(pattern in url_lower for pattern in ['legal', 'privacy', 'terms', 'cookie']):
            return True
        
        # Redirect-only
        if page.get('status_code') in [301, 302, 307, 308]:
            return True
        
        # Pagination
        if 'page=' in url_lower or '/page/' in url_lower:
            return True
        
        # Search result pages
        if '/search' in url_lower or '?q=' in url_lower:
            return True
        
        return False
    
    def calculate_priority_score(self, page: Dict, quality: Dict, 
                                 indexability: Dict, link_graph: Dict,
                                 canonical: Dict) -> float:
        """
        Calculate priority score using the canonical formula.
        
        Formula:
        priority_score = (
            authority_score * 0.35 +
            quality_score * 0.25 +
            indexability_score * 0.20 +
            canonical_health * 0.15 -
            crawl_waste_penalty * 0.15
        )
        
        Args:
            page: Page data
            quality: Quality data
            indexability: Indexability data
            link_graph: Link graph data
            canonical: Canonical data
            
        Returns:
            Priority score (0.0-1.0)
        """
        # Component 1: Authority score (0.35 weight)
        authority_score = link_graph.get('pagerank', 0.0) if link_graph else 0.0
        # Normalize PageRank (typically 0-1 already, but ensure)
        authority_score = min(max(authority_score, 0.0), 1.0)
        
        # Component 2: Quality score (0.25 weight)
        quality_score = quality.get('quality_score', 0.0) if quality else 0.0
        quality_score = min(max(quality_score, 0.0), 1.0)
        
        # Component 3: Indexability score (0.20 weight)
        # Convert indexability status to score
        indexability_status = indexability.get('indexability_status', 'NON_INDEXABLE') if indexability else 'NON_INDEXABLE'
        if indexability_status == 'INDEXABLE_AND_VALID':
            indexability_score = 1.0
        elif indexability_status == 'INDEXABLE_BUT_NOT_ELIGIBLE':
            indexability_score = 0.6
        else:
            indexability_score = 0.0
        
        # Component 4: Canonical health (0.15 weight)
        canonical_info = canonical.get('canonical_info', {}) if canonical else {}
        is_leader = canonical_info.get('is_cluster_leader', False)
        canonical_health = 1.0 if is_leader else 0.3
        
        # Component 5: Crawl waste penalty (0.15 weight)
        crawl_budget_impact = indexability.get('crawl_budget_impact', {}) if indexability else {}
        is_waste = crawl_budget_impact.get('is_waste', False)
        crawl_waste_penalty = 0.8 if is_waste else 0.0
        
        # Calculate final score
        priority_score = (
            authority_score * 0.35 +
            quality_score * 0.25 +
            indexability_score * 0.20 +
            canonical_health * 0.15 -
            crawl_waste_penalty * 0.15
        )
        
        # Clamp between 0.0 and 1.0
        return round(min(max(priority_score, 0.0), 1.0), 3)
    
    def determine_priority_tier(self, score: float, estimated_impact: str) -> str:
        """
        Map priority score to tier.
        
        POLISH 1: Added controlled HIGH tier rule
        
        Args:
            score: Priority score (0.0-1.0)
            estimated_impact: Estimated impact (HIGH/MEDIUM/LOW)
            
        Returns:
            Priority tier
        """
        if score >= 0.80:
            return "CRITICAL"
        # POLISH 1: Controlled HIGH tier - only if score > 0.65 AND impact = HIGH
        elif score >= 0.65 and estimated_impact == "HIGH":
            return "HIGH"
        elif score >= 0.60:
            return "HIGH"
        elif score >= 0.40:
            return "MEDIUM"
        else:
            return "LOW"
    
    def estimate_effort(self, quality: Dict, indexability: Dict, canonical: Dict) -> str:
        """
        Estimate effort level for fixes.
        
        Rules:
        - Canonical fix: LOW
        - Internal linking: LOW
        - Redirect cleanup: MEDIUM
        - Content expansion: HIGH
        - Structural index change: HIGH
        
        If multiple fixes exist → pick highest effort.
        
        Args:
            quality: Quality data
            indexability: Indexability data
            canonical: Canonical data
            
        Returns:
            Effort level (LOW/MEDIUM/HIGH)
        """
        efforts = []
        
        # Check for content expansion need
        recommended_action = quality.get('recommended_action', '') if quality else ''
        if recommended_action in ['expand', 'improve']:
            efforts.append('HIGH')
        
        # Check for canonical issues
        canonical_info = canonical.get('canonical_info', {}) if canonical else {}
        if not canonical_info.get('is_cluster_leader', True):
            efforts.append('LOW')
        
        # Check for indexability issues
        indexing_signals = indexability.get('indexing_signals', {}) if indexability else {}
        if indexing_signals.get('redirected', False):
            efforts.append('MEDIUM')
        if indexing_signals.get('noindex', False):
            efforts.append('LOW')
        
        # Check for internal linking needs
        internal_authority = quality.get('internal_authority', {}) if quality else {}
        if internal_authority.get('inlinks', 0) < 3:
            efforts.append('LOW')
        
        # Return highest effort
        if 'HIGH' in efforts:
            return 'HIGH'
        elif 'MEDIUM' in efforts:
            return 'MEDIUM'
        elif 'LOW' in efforts:
            return 'LOW'
        else:
            return 'LOW'
    
    def estimate_impact(self, authority_score: float, indexability_score: float, 
                       effort_level: str) -> str:
        """
        Estimate impact of fixing the page.
        
        Impact ≠ Priority
        
        Rules:
        - High authority + blocked: HIGH
        - Medium authority + easy fix: MEDIUM
        - Low authority + heavy effort: LOW
        
        Args:
            authority_score: Authority score
            indexability_score: Indexability score
            effort_level: Effort level
            
        Returns:
            Impact level (HIGH/MEDIUM/LOW)
        """
        # High authority + blocked
        if authority_score >= 0.7 and indexability_score < 0.5:
            return "HIGH"
        
        # Medium authority + easy fix
        if authority_score >= 0.4 and effort_level == "LOW":
            return "MEDIUM"
        
        # High authority regardless
        if authority_score >= 0.7:
            return "HIGH"
        
        # Medium authority
        if authority_score >= 0.3:
            return "MEDIUM"
        
        # Default: LOW
        return "LOW"
    
    def generate_quick_wins(self, page: Dict, quality: Dict, indexability: Dict, 
                           canonical: Dict) -> List[str]:
        """
        Generate 1-3 actionable quick wins.
        
        POLISH 2: De-duplicate internal_links quick wins
        
        Args:
            page: Page data
            quality: Quality data
            indexability: Indexability data
            canonical: Canonical data
            
        Returns:
            List of quick win recommendations
        """
        quick_wins = []
        internal_links_added = False  # POLISH 2: Track if internal links already added
        
        # Canonical issues
        canonical_info = canonical.get('canonical_info', {}) if canonical else {}
        if not canonical_info.get('is_cluster_leader', True):
            quick_wins.append("Fix self-canonical mismatch")
        
        # Indexability issues
        indexing_signals = indexability.get('indexing_signals', {}) if indexability else {}
        if indexing_signals.get('noindex', False):
            quick_wins.append("Remove noindex tag")
        
        if indexing_signals.get('redirected', False):
            quick_wins.append("Update internal links to final URL")
        
        # Internal linking - POLISH 2: Only add once
        internal_authority = quality.get('internal_authority', {}) if quality else {}
        inlinks = internal_authority.get('inlinks', 0)
        if not internal_links_added:
            if inlinks == 0:
                quick_wins.append("Add internal links from related pages")
                internal_links_added = True
            elif inlinks < 3:
                quick_wins.append("Add 2-3 more internal links from cluster hubs")
                internal_links_added = True
        
        # Content expansion
        recommended_action = quality.get('recommended_action', '') if quality else ''
        if recommended_action == 'expand' and not internal_links_added:
            word_count = quality.get('word_count', 0)
            target = 800 if word_count < 400 else 1200
            quick_wins.append(f"Expand content to {target}+ words")
        
        # Consolidation
        if recommended_action == 'consolidate':
            quick_wins.append("Consolidate to cluster leader")
        
        # Return max 3
        return quick_wins[:3]
    
    def generate_primary_reason(self, priority_score: float, quality: Dict, 
                                indexability: Dict, canonical: Dict,
                                authority_score: float) -> str:
        """
        Generate human-readable primary reason for priority.
        
        Args:
            priority_score: Priority score
            quality: Quality data
            indexability: Indexability data
            canonical: Canonical data
            authority_score: Authority score
            
        Returns:
            Primary reason string
        """
        # High priority reasons
        if priority_score >= 0.80:
            if authority_score >= 0.7:
                indexability_status = indexability.get('indexability_status', '') if indexability else ''
                if indexability_status != 'INDEXABLE_AND_VALID':
                    return "High authority page blocked by indexability issues"
                
                canonical_info = canonical.get('canonical_info', {}) if canonical else {}
                if not canonical_info.get('is_cluster_leader', True):
                    return "High authority page blocked by canonical misconfiguration"
            
            return "High-impact optimization opportunity"
        
        # Medium-high priority
        elif priority_score >= 0.60:
            quality_grade = quality.get('quality_grade', '') if quality else ''
            if quality_grade in ['C', 'D']:
                return "Medium authority page with fixable quality issues"
            
            return "Significant improvement opportunity"
        
        # Medium priority
        elif priority_score >= 0.40:
            return "Moderate optimization potential"
        
        # Low priority
        else:
            return "Low priority optimization"
    
    def get_fix_categories(self, quality: Dict, indexability: Dict, canonical: Dict) -> List[str]:
        """
        Get fix categories for the page.
        
        Args:
            quality: Quality data
            indexability: Indexability data
            canonical: Canonical data
            
        Returns:
            List of fix categories
        """
        categories = []
        
        # Canonical
        canonical_info = canonical.get('canonical_info', {}) if canonical else {}
        if not canonical_info.get('is_cluster_leader', True):
            categories.append("canonical")
        
        # Indexability
        indexing_signals = indexability.get('indexing_signals', {}) if indexability else {}
        if indexing_signals.get('noindex', False) or indexing_signals.get('redirected', False):
            categories.append("indexability")
        
        # Internal links
        internal_authority = quality.get('internal_authority', {}) if quality else {}
        if internal_authority.get('inlinks', 0) < 3:
            categories.append("internal_links")
        
        # Content
        recommended_action = quality.get('recommended_action', '') if quality else ''
        if recommended_action in ['expand', 'improve']:
            categories.append("content_quality")
        
        # Crawl budget
        crawl_budget_impact = indexability.get('crawl_budget_impact', {}) if indexability else {}
        if crawl_budget_impact.get('is_waste', False):
            categories.append("crawl_budget")
        
        return categories
    
    def analyze(self):
        """Run the complete priority analysis."""
        print("Analyzing page priorities...\n")
        
        for page in self.pages:
            url = page['url']
            
            # Get data from each module
            quality = self.quality_data.get(url, {})
            indexability = self.indexability_data.get(url, {})
            link_graph = self.link_graph_data.get(url, {})
            canonical = self.canonical_data.get(url, {})
            
            # Check for auto-demotion
            if self.should_auto_demote(page, quality, indexability):
                priority_tier = "IGNORE"
                priority_score = 0.0
                estimated_impact = "LOW"
                effort_level = "LOW"
                primary_reason = "Auto-demoted (utility/legal/redirect page)"
                fix_categories = []
                quick_wins = []
            else:
                # Calculate priority score
                priority_score = self.calculate_priority_score(
                    page, quality, indexability, link_graph, canonical
                )
                
                # Extract component scores for traceability (POLISH 3)
                authority_score = link_graph.get('pagerank', 0.0) if link_graph else 0.0
                quality_score = quality.get('quality_score', 0.0) if quality else 0.0
                indexability_status = indexability.get('indexability_status', 'NON_INDEXABLE') if indexability else 'NON_INDEXABLE'
                indexability_score = 1.0 if indexability_status == 'INDEXABLE_AND_VALID' else 0.6 if indexability_status == 'INDEXABLE_BUT_NOT_ELIGIBLE' else 0.0
                canonical_info_data = canonical.get('canonical_info', {}) if canonical else {}
                is_leader = canonical_info_data.get('is_cluster_leader', False)
                canonical_health = 1.0 if is_leader else 0.3
                crawl_budget_impact = indexability.get('crawl_budget_impact', {}) if indexability else {}
                is_waste = crawl_budget_impact.get('is_waste', False)
                crawl_waste_penalty = 0.8 if is_waste else 0.0
                
                # Estimate effort and impact
                effort_level = self.estimate_effort(quality, indexability, canonical)
                estimated_impact = self.estimate_impact(authority_score, indexability_score, effort_level)
                
                # Determine tier - POLISH 1: Pass estimated_impact
                priority_tier = self.determine_priority_tier(priority_score, estimated_impact)
                
                # Generate metadata
                primary_reason = self.generate_primary_reason(
                    priority_score, quality, indexability, canonical, authority_score
                )
                fix_categories = self.get_fix_categories(quality, indexability, canonical)
                quick_wins = self.generate_quick_wins(page, quality, indexability, canonical)
                
                # POLISH 3: Add traceability fields
                score_breakdown = {
                    "authority_score": round(authority_score, 3),
                    "quality_score": round(quality_score, 3),
                    "indexability_score": round(indexability_score, 3),
                    "canonical_health": round(canonical_health, 3),
                    "crawl_waste_penalty": round(crawl_waste_penalty, 3)
                }
                
                inputs_used = {
                    "has_quality_data": bool(quality),
                    "has_indexability_data": bool(indexability),
                    "has_link_graph_data": bool(link_graph),
                    "has_canonical_data": bool(canonical)
                }
            
            # Build priority entry
            priority_entry = {
                "url": url,
                "priority_score": priority_score,
                "priority_tier": priority_tier,
                "estimated_impact": estimated_impact,
                "effort_level": effort_level,
                "primary_reason": primary_reason,
                "fix_categories": fix_categories,
                "quick_wins": quick_wins,
                "score_breakdown": score_breakdown,  # POLISH 3: Traceability
                "inputs_used": inputs_used  # POLISH 3: Traceability
            }
            
            self.priority_scores.append(priority_entry)
        
        print(f"Analyzed {len(self.priority_scores)} pages\n")
    
    def export_results(self):
        """Export priority scores and summary."""
        print("Generating priority reports...\n")
        
        # Generate page_priority_scores.json
        scores_file = self.output_dir / f"{self.base_name}_page_priority_scores.json"
        with open(scores_file, 'w', encoding='utf-8') as f:
            json.dump(self.priority_scores, f, indent=2, ensure_ascii=False)
        print(f"  ✓ {scores_file.name}")
        
        # Generate summary
        total_pages = len(self.priority_scores)
        priority_distribution = defaultdict(int)
        fix_categories_count = defaultdict(int)
        
        for entry in self.priority_scores:
            priority_distribution[entry['priority_tier']] += 1
            for category in entry['fix_categories']:
                fix_categories_count[category] += 1
        
        summary = {
            "total_pages": total_pages,
            "priority_distribution": dict(priority_distribution),
            "top_opportunity_types": dict(sorted(fix_categories_count.items(), key=lambda x: x[1], reverse=True))
        }
        
        summary_file = self.output_dir / f"{self.base_name}_page_priority_summary.json"
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        print(f"  ✓ {summary_file.name}")
        
        print("\n" + "=" * 70)
        print("📊 PAGE PRIORITY ANALYSIS COMPLETE")
        print("=" * 70)
        print(f"\n  Total Pages: {total_pages}")
        print(f"\n  Priority Distribution:")
        for tier in ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'IGNORE']:
            count = priority_distribution.get(tier, 0)
            if count > 0:
                print(f"    {tier}: {count}")
        
        print(f"\n  Top Fix Opportunities:")
        for category, count in list(summary['top_opportunity_types'].items())[:5]:
            print(f"    {category}: {count}")
        
        print("\n" + "=" * 70 + "\n")
    
    def run(self):
        """Run the complete priority engine."""
        self.load_data()
        self.analyze()
        self.export_results()


def main():
    """Main entry point."""
    print("=" * 70)
    print("📊 PAGE PRIORITY ENGINE")
    print("=" * 70)
    print()
    
    # Ask user which input method they prefer
    print("Choose input method:")
    print("  1. Auto-detect all files from pages.json (recommended)")
    print("  2. Specify each input file individually")
    print()
    method = input("Enter choice (1 or 2, default=1): ").strip()
    
    if method == "2":
        # Method 2: Specify each file individually
        print("\n" + "=" * 70)
        print("Enter paths to input files:")
        print("=" * 70)
        print()
        
        print("Required files:")
        pages_path = input("  1. pages.json: ").strip()
        quality_path = input("  2. content_quality_pages.json: ").strip()
        indexability_path = input("  3. indexability_pages.json: ").strip()
        link_graph_path = input("  4. link_graph.json: ").strip()
        canonical_path = input("  5. canonical_clusters_page_index.json: ").strip()
        
        print("\nOptional files (press Enter to skip):")
        redirect_path = input("  6. redirect_map.json (optional): ").strip()
        
        # Validate required files
        if not all([pages_path, quality_path, indexability_path, link_graph_path, canonical_path]):
            print("\nError: All required files must be provided")
            return
        
        # Check if files exist
        for path in [pages_path, quality_path, indexability_path, link_graph_path, canonical_path]:
            if not os.path.exists(path):
                print(f"\nError: File not found: {path}")
                return
        
        # Load data manually
        print("\n" + "=" * 70)
        print("📊 PAGE PRIORITY ENGINE")
        print("=" * 70)
        print("\nLoading input files...\n")
        
        # Determine output directory from pages.json
        output_dir = Path(pages_path).parent
        base_name = Path(pages_path).stem.replace('_pages', '')
        
        # Create engine with custom paths
        engine = PagePriorityEngine(str(output_dir / base_name))
        
        # Load files manually
        print(f"  ✓ Loading {Path(pages_path).name}...")
        with open(pages_path, 'r', encoding='utf-8') as f:
            engine.pages = json.load(f)
        print(f"    Loaded {len(engine.pages)} pages")
        
        print(f"  ✓ Loading {Path(quality_path).name}...")
        with open(quality_path, 'r', encoding='utf-8') as f:
            quality_pages = json.load(f)
            engine.quality_data = {p['url']: p for p in quality_pages}
        print(f"    Loaded {len(engine.quality_data)} quality records")
        
        print(f"  ✓ Loading {Path(indexability_path).name}...")
        with open(indexability_path, 'r', encoding='utf-8') as f:
            indexability_pages = json.load(f)
            engine.indexability_data = {p['url']: p for p in indexability_pages}
        print(f"    Loaded {len(engine.indexability_data)} indexability records")
        
        print(f"  ✓ Loading {Path(link_graph_path).name}...")
        with open(link_graph_path, 'r', encoding='utf-8') as f:
            link_graph = json.load(f)
            engine.link_graph_data = {node['url']: node for node in link_graph.get('nodes', [])}
        print(f"    Loaded {len(engine.link_graph_data)} link graph nodes")
        
        print(f"  ✓ Loading {Path(canonical_path).name}...")
        with open(canonical_path, 'r', encoding='utf-8') as f:
            engine.canonical_data = json.load(f)
        print(f"    Loaded {len(engine.canonical_data)} canonical records")
        
        if redirect_path and os.path.exists(redirect_path):
            print(f"  ✓ Loading {Path(redirect_path).name}...")
            with open(redirect_path, 'r', encoding='utf-8') as f:
                engine.redirect_map = json.load(f)
            print(f"    Loaded {len(engine.redirect_map)} redirect mappings")
        
        print("\nData loading complete.\n")
        
        # Run analysis
        engine.analyze()
        engine.export_results()
        
    else:
        # Method 1: Auto-detect from pages.json (default)
        print()
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
        print("📊 PAGE PRIORITY ENGINE")
        print("=" * 70)
        print()
        
        # Run analysis
        engine = PagePriorityEngine(base_path)
        engine.run()


if __name__ == "__main__":
    main()
