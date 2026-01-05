#!/usr/bin/env python3
"""
SEO Change Impact Tracking Engine

Compares baseline (before) and post-fix (after) crawl snapshots to quantify 
the impact of implemented SEO fixes.

Answers: "Did the SEO fixes we implemented actually improve the site?"

This module measures REAL changes, not assumptions. It validates that fixes actually worked.
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from collections import defaultdict
from datetime import datetime


# Grade values for impact calculation
GRADE_VALUES = {'A': 4, 'B': 3, 'C': 2, 'D': 1}


class ChangeImpactTracker:
    """
    SEO Change Impact Tracking Engine - Measures effectiveness of SEO fixes.
    
    Compares before/after snapshots to quantify:
    - Page-level improvements
    - Fix-level success rates
    - Overall SEO performance gains
    """
    
    def __init__(self, before_path: str, after_path: str):
        """
        Initialize Change Impact Tracker.
        
        Args:
            before_path: Path to baseline snapshot
            after_path: Path to post-fix snapshot
        """
        self.before_path = before_path
        self.after_path = after_path
        self.output_dir = Path(before_path).parent
        
        # Data storage
        self.before_data = {}
        self.after_data = {}
        self.redirect_map = {}
        self.execution_plan = {}
        
        # Results
        self.page_impacts = []
        self.fix_attributions = {}
    
    def load_snapshots(self):
        """Load before and after snapshots."""
        print("Loading snapshots...\n")
        
        # Load BEFORE snapshot
        print(f"  ✓ Loading BEFORE snapshot: {Path(self.before_path).name}")
        try:
            with open(self.before_path, 'r', encoding='utf-8') as f:
                before_snapshot = json.load(f)
                # Handle both formats: direct dict or wrapped
                if 'pages' in before_snapshot:
                    pages = before_snapshot['pages']
                else:
                    pages = before_snapshot
                
                self.before_data = {p['url']: p for p in pages if isinstance(p, dict)}
            print(f"    Loaded {len(self.before_data)} pages")
        except FileNotFoundError:
            print(f"    ✗ Error: {Path(self.before_path).name} not found")
            raise
        
        # Load AFTER snapshot
        print(f"  ✓ Loading AFTER snapshot: {Path(self.after_path).name}")
        try:
            with open(self.after_path, 'r', encoding='utf-8') as f:
                after_snapshot = json.load(f)
                # Handle both formats
                if 'pages' in after_snapshot:
                    pages = after_snapshot['pages']
                else:
                    pages = after_snapshot
                
                self.after_data = {p['url']: p for p in pages if isinstance(p, dict)}
            print(f"    Loaded {len(self.after_data)} pages")
        except FileNotFoundError:
            print(f"    ✗ Error: {Path(self.after_path).name} not found")
            raise
        
        # Optional: Load redirect map
        base_path = str(Path(self.before_path).parent / Path(self.before_path).stem.replace('_pages', ''))
        redirect_file = f"{base_path}_pages_redirect_map.json"
        if os.path.exists(redirect_file):
            print(f"  ✓ Loading redirect map (OPTIONAL)...")
            with open(redirect_file, 'r', encoding='utf-8') as f:
                redirect_data = json.load(f)
                self.redirect_map = {
                    url: data.get('final_url', url)
                    for url, data in redirect_data.items()
                    if isinstance(data, dict)
                }
            print(f"    Loaded {len(self.redirect_map)} redirect mappings")
        
        # Optional: Load execution plan
        plan_file = f"{base_path}_execution_plan.json"
        if os.path.exists(plan_file):
            print(f"  ✓ Loading execution plan (OPTIONAL)...")
            with open(plan_file, 'r', encoding='utf-8') as f:
                plan_data = json.load(f)
                tasks = plan_data.get('tasks', [])
                self.execution_plan = {task['url']: task for task in tasks}
            print(f"    Loaded {len(self.execution_plan)} planned tasks")
        
        print("\nSnapshot loading complete.\n")
    
    def resolve_url(self, url: str) -> str:
        """
        Resolve URL using redirect map.
        
        Args:
            url: URL to resolve
            
        Returns:
            Resolved URL
        """
        # Step 1: Resolve redirects
        final_url = self.redirect_map.get(url, url)
        
        # Step 2: Could apply canonical here, but we'll keep it simple
        # since we're comparing snapshots that already have canonical data
        
        return final_url
    
    def diff_page_signals(self, before: Dict, after: Dict) -> List[str]:
        """
        Detect changes between before and after page data.
        
        Args:
            before: Before page data
            after: After page data
            
        Returns:
            List of detected changes
        """
        changes = []
        
        # Indexability change
        before_indexable = before.get('indexable', before.get('is_indexable', False))
        after_indexable = after.get('indexable', after.get('is_indexable', False))
        
        if before_indexable != after_indexable:
            if after_indexable:
                changes.append('indexability_restored')
            else:
                changes.append('indexability_lost')
        
        # Canonical status change
        before_canonical = before.get('canonical_status', 'UNKNOWN')
        after_canonical = after.get('canonical_status', 'UNKNOWN')
        
        if before_canonical != after_canonical:
            if after_canonical == 'OK':
                changes.append('canonical_fixed')
            elif before_canonical == 'OK':
                changes.append('canonical_broken')
        
        # Quality grade change
        before_grade = before.get('quality_grade', 'D')
        after_grade = after.get('quality_grade', 'D')
        
        if before_grade != after_grade:
            changes.append(f'quality_{before_grade}_to_{after_grade}')
        
        # Priority score change (significant if > 0.1)
        before_priority = before.get('priority_score', 0)
        after_priority = after.get('priority_score', 0)
        priority_change = after_priority - before_priority
        
        if abs(priority_change) > 0.1:
            if priority_change > 0:
                changes.append('priority_increased')
            else:
                changes.append('priority_decreased')
        
        # Authority change (PageRank)
        before_authority = before.get('pagerank', before.get('authority_score', 0))
        after_authority = after.get('pagerank', after.get('authority_score', 0))
        authority_change = after_authority - before_authority
        
        if abs(authority_change) > 0.001:
            if authority_change > 0:
                changes.append('authority_increased')
            else:
                changes.append('authority_decreased')
        
        return changes
    
    def calculate_impact_score(self, before: Dict, after: Dict) -> float:
        """
        Calculate impact score for a page.
        
        Formula: priority_change + indexability_bonus + quality_bonus + canonical_bonus
        
        Args:
            before: Before page data
            after: After page data
            
        Returns:
            Impact score
        """
        impact = 0.0
        
        # Priority score change (primary metric)
        before_priority = before.get('priority_score', 0)
        after_priority = after.get('priority_score', 0)
        impact += (after_priority - before_priority)
        
        # Indexability bonus
        before_indexable = before.get('indexable', before.get('is_indexable', False))
        after_indexable = after.get('indexable', after.get('is_indexable', False))
        
        if not before_indexable and after_indexable:
            impact += 0.15
        elif before_indexable and not after_indexable:
            impact -= 0.15
        
        # Quality grade bonus
        before_grade = before.get('quality_grade', 'D')
        after_grade = after.get('quality_grade', 'D')
        
        before_value = GRADE_VALUES.get(before_grade, 1)
        after_value = GRADE_VALUES.get(after_grade, 1)
        grade_diff = after_value - before_value
        
        if grade_diff == 1:  # D→C or C→B or B→A
            impact += 0.05
        elif grade_diff == 2:  # D→B or C→A
            impact += 0.08
        elif grade_diff >= 3:  # D→A
            impact += 0.12
        elif grade_diff < 0:  # Regression
            impact += (grade_diff * 0.05)
        
        # Canonical fix bonus
        before_canonical = before.get('canonical_status', 'UNKNOWN')
        after_canonical = after.get('canonical_status', 'UNKNOWN')
        
        if before_canonical != 'OK' and after_canonical == 'OK':
            impact += 0.06
        elif before_canonical == 'OK' and after_canonical != 'OK':
            impact -= 0.06
        
        return round(impact, 3)
    
    def classify_status(self, impact_score: float) -> str:
        """
        Classify page status based on impact score.
        
        Args:
            impact_score: Impact score
            
        Returns:
            Status (IMPROVED/REGRESSED/UNCHANGED)
        """
        if impact_score > 0.1:
            return 'IMPROVED'
        elif impact_score < -0.05:
            return 'REGRESSED'
        else:
            return 'UNCHANGED'
    
    def attribute_to_fixes(self, changes: List[str], url: str) -> List[str]:
        """
        Attribute detected changes to executed fixes.
        
        Args:
            changes: List of detected changes
            url: Page URL
            
        Returns:
            List of fix types
        """
        fix_types = set()
        
        for change in changes:
            if 'canonical' in change:
                fix_types.add('canonical_fix')
            elif 'indexability' in change:
                fix_types.add('indexability_fix')
            elif 'quality' in change:
                fix_types.add('content_fix')
            elif 'authority' in change or 'priority' in change:
                fix_types.add('link_fix')
        
        return list(fix_types)
    
    def analyze_impacts(self):
        """Analyze impacts for all pages."""
        print("Analyzing page impacts...\n")
        
        # Get all unique URLs (from both snapshots)
        all_urls = set(self.before_data.keys()) | set(self.after_data.keys())
        
        for url in all_urls:
            # Resolve URL
            resolved_url = self.resolve_url(url)
            
            # Get before/after data
            before = self.before_data.get(url, {})
            after = self.after_data.get(url, {})
            
            # Skip if page only exists in one snapshot
            if not before or not after:
                continue
            
            # Detect changes
            changes = self.diff_page_signals(before, after)
            
            # Calculate impact
            impact_score = self.calculate_impact_score(before, after)
            status = self.classify_status(impact_score)
            
            # Attribute to fixes
            fix_types = self.attribute_to_fixes(changes, url)
            
            # Build impact record
            impact = {
                'url': url,
                'changes_detected': changes,
                'before': {
                    'indexable': before.get('indexable', before.get('is_indexable', False)),
                    'quality_grade': before.get('quality_grade', 'D'),
                    'priority_score': before.get('priority_score', 0),
                    'canonical_status': before.get('canonical_status', 'UNKNOWN')
                },
                'after': {
                    'indexable': after.get('indexable', after.get('is_indexable', False)),
                    'quality_grade': after.get('quality_grade', 'D'),
                    'priority_score': after.get('priority_score', 0),
                    'canonical_status': after.get('canonical_status', 'UNKNOWN')
                },
                'impact_score': impact_score,
                'status': status,
                'attributed_fixes': fix_types
            }
            
            self.page_impacts.append(impact)
            
            # Track fix attributions
            for fix_type in fix_types:
                if fix_type not in self.fix_attributions:
                    self.fix_attributions[fix_type] = {
                        'pages': [],
                        'impact_scores': []
                    }
                self.fix_attributions[fix_type]['pages'].append(url)
                self.fix_attributions[fix_type]['impact_scores'].append(impact_score)
        
        print(f"Analyzed {len(self.page_impacts)} pages\n")
    
    def generate_reports(self):
        """Generate all output reports."""
        print("Generating impact reports...\n")
        
        # 1. Page Impact Report
        page_report_file = self.output_dir / "page_impact_report.json"
        page_report = {"pages": self.page_impacts}
        with open(page_report_file, 'w', encoding='utf-8') as f:
            json.dump(page_report, f, indent=2, ensure_ascii=False)
        print(f"  ✓ {page_report_file.name}")
        
        # 2. Fix Attribution Report
        fix_report = self.generate_fix_attribution_report()
        fix_report_file = self.output_dir / "fix_attribution_report.json"
        with open(fix_report_file, 'w', encoding='utf-8') as f:
            json.dump(fix_report, f, indent=2, ensure_ascii=False)
        print(f"  ✓ {fix_report_file.name}")
        
        # 3. Executive Summary
        summary = self.generate_executive_summary()
        summary_file = self.output_dir / "impact_executive_summary.json"
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        print(f"  ✓ {summary_file.name}")
        
        # Print summary
        print("\n" + "=" * 70)
        print("📊 SEO CHANGE IMPACT TRACKING COMPLETE")
        print("=" * 70)
        print(f"\n  Total Pages Tracked: {summary['total_pages_tracked']}")
        print(f"  Pages Improved: {summary['pages_improved']}")
        print(f"  Pages Regressed: {summary['pages_regressed']}")
        print(f"  Pages Unchanged: {summary['pages_unchanged']}")
        print(f"\n  Average Priority Gain: {summary['avg_priority_gain']}")
        print(f"  High Confidence Wins: {summary['high_confidence_wins']}")
        
        if summary.get('top_improvements'):
            print(f"\n  Top Improvements:")
            for improvement in summary['top_improvements'][:3]:
                print(f"    - {improvement}")
        
        print("\n" + "=" * 70 + "\n")
    
    def generate_fix_attribution_report(self) -> Dict:
        """Generate fix attribution report."""
        fixes = []
        
        for fix_type, data in self.fix_attributions.items():
            pages_affected = len(data['pages'])
            impact_scores = data['impact_scores']
            
            # Calculate success rate (pages with positive impact)
            pages_improved = sum(1 for score in impact_scores if score > 0.1)
            success_rate = pages_improved / pages_affected if pages_affected > 0 else 0
            
            # Calculate average impact
            avg_impact = sum(impact_scores) / len(impact_scores) if impact_scores else 0
            
            # Calculate average priority lift
            avg_priority_lift = avg_impact  # Simplified
            
            fixes.append({
                'fix_type': fix_type,
                'pages_affected': pages_affected,
                'pages_improved': pages_improved,
                'success_rate': round(success_rate, 2),
                'avg_priority_lift': round(avg_priority_lift, 3),
                'avg_impact_score': round(avg_impact, 3)
            })
        
        # Sort by pages affected
        fixes.sort(key=lambda x: x['pages_affected'], reverse=True)
        
        return {'fixes': fixes}
    
    def generate_executive_summary(self) -> Dict:
        """Generate executive summary."""
        total_pages = len(self.page_impacts)
        
        # Count by status
        improved = sum(1 for p in self.page_impacts if p['status'] == 'IMPROVED')
        regressed = sum(1 for p in self.page_impacts if p['status'] == 'REGRESSED')
        unchanged = sum(1 for p in self.page_impacts if p['status'] == 'UNCHANGED')
        
        # Calculate average priority gain
        priority_gains = [
            p['after']['priority_score'] - p['before']['priority_score']
            for p in self.page_impacts
        ]
        avg_priority_gain = sum(priority_gains) / len(priority_gains) if priority_gains else 0
        
        # High confidence wins (impact > 0.2)
        high_confidence_wins = sum(1 for p in self.page_impacts if p['impact_score'] > 0.2)
        
        # Top improvements
        top_improvements = []
        for fix_type, data in self.fix_attributions.items():
            pages_improved = sum(1 for score in data['impact_scores'] if score > 0.1)
            if pages_improved > 0:
                top_improvements.append(f"{fix_type.replace('_', ' ').title()}: {pages_improved} pages improved")
        
        # Sort by number of pages
        top_improvements.sort(key=lambda x: int(x.split(':')[1].split()[0]), reverse=True)
        
        return {
            'total_pages_tracked': total_pages,
            'pages_improved': improved,
            'pages_regressed': regressed,
            'pages_unchanged': unchanged,
            'avg_priority_gain': f"+{avg_priority_gain:.2f}" if avg_priority_gain > 0 else f"{avg_priority_gain:.2f}",
            'high_confidence_wins': high_confidence_wins,
            'top_improvements': top_improvements
        }
    
    def run(self):
        """Run the complete change impact tracking."""
        self.load_snapshots()
        self.analyze_impacts()
        self.generate_reports()


def main():
    """Main entry point."""
    print("=" * 70)
    print("📊 SEO CHANGE IMPACT TRACKING ENGINE")
    print("=" * 70)
    print()
    
    # Get input paths
    print("Enter path to BEFORE snapshot (baseline):")
    print("Example: crawler_output/developer_mozilla_org_20251220_054821_pages.json")
    print()
    before_path = input("BEFORE snapshot path: ").strip()
    
    if not before_path:
        print("Error: No path provided")
        return
    
    print()
    print("Enter path to AFTER snapshot (post-fix):")
    print("Example: crawler_output/developer_mozilla_org_20251222_031422_pages.json")
    print()
    after_path = input("AFTER snapshot path: ").strip()
    
    if not after_path:
        print("Error: No path provided")
        return
    
    # Check if files exist
    if not os.path.exists(before_path):
        print(f"Error: BEFORE file not found: {before_path}")
        return
    
    if not os.path.exists(after_path):
        print(f"Error: AFTER file not found: {after_path}")
        return
    
    print()
    print("=" * 70)
    print("📊 SEO CHANGE IMPACT TRACKING ENGINE")
    print("=" * 70)
    print()
    
    # Run tracker
    tracker = ChangeImpactTracker(before_path, after_path)
    tracker.run()


if __name__ == "__main__":
    main()
