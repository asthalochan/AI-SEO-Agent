#!/usr/bin/env python3
"""
Change Impact Tracker - The Truth Engine

Validates SEO progress by comparing before/after snapshots.

Answers:
- Did indexability improve?
- Did canonical issues drop?
- Did internal authority shift?
- Did priority scores increase?
- Which fixes actually worked?

Core Principle: Impact = Delta (No re-analysis, only comparison)
"""

import json
import argparse
import sys
from pathlib import Path
from typing import Dict, List, Any, Tuple, Optional
from collections import defaultdict
from datetime import datetime


class ChangeImpactTracker:
    """
    Change Impact Tracker - Validates SEO progress through snapshot comparison.
    
    This module NEVER re-runs analysis. It only compares existing data.
    """
    
    def __init__(self, snapshot_before: str, snapshot_after: str, output_dir: Optional[str] = None):
        """
        Initialize Change Impact Tracker.
        
        Args:
            snapshot_before: Path to before snapshot directory
            snapshot_after: Path to after snapshot directory
            output_dir: Optional output directory (defaults to after_snapshot/impact_analysis/)
        """
        self.before_path = Path(snapshot_before)
        self.after_path = Path(snapshot_after)
        
        # Default: save in after snapshot's impact_analysis folder
        if output_dir:
            self.output_dir = Path(output_dir)
        else:
            self.output_dir = self.after_path / "impact_analysis"
        
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Extract snapshot timestamps from directory names
        self.before_timestamp = self.before_path.name
        self.after_timestamp = self.after_path.name
        
        # Loaded snapshots
        self.before = {}
        self.after = {}
        
        # Results
        self.page_impacts = []
        self.metrics_delta = {}
        self.summary = {}
        self.winners = []
        self.failures = []
        
        print(f"\n📊 Change Impact Tracker")
        print(f"Before: {self.before_timestamp}")
        print(f"After:  {self.after_timestamp}")
        print()
    
    def load_snapshot(self, path: Path, label: str) -> Dict[str, Any]:
        """
        Load all required files from a snapshot directory.
        
        Args:
            path: Path to snapshot directory
            label: Label for logging (before/after)
            
        Returns:
            Dictionary containing all snapshot data
        """
        print(f"Loading {label} snapshot from {path.name}...")
        
        snapshot = {}
        
        # Required files
        required_files = {
            'summary': 'crawler_summary.json',
            'pages': 'crawler_pages.json',
            'indexability': 'crawler_indexability_pages.json',
            'canonical_clusters': 'crawler_pages_canonical_clusters_page_index.json',
            'priority': 'crawler_page_priority_scores.json',
            'content_quality': 'crawler_content_quality_pages.json',
        }
        
        # Optional files
        optional_files = {
            'redirect_map': 'crawler_pages_redirect_map.json',
            'redirect_summary': 'crawler_pages_redirect_summary.json',
            'seo_fix_summary': 'crawler_seo_fix_summary.json',
            'metadata': 'activation_metadata.json',
        }
        
        # Load required files
        for key, filename in required_files.items():
            file_path = path / filename
            if not file_path.exists():
                raise FileNotFoundError(f"Required file missing: {filename}")
            
            with open(file_path, 'r', encoding='utf-8') as f:
                snapshot[key] = json.load(f)
            print(f"  ✓ {filename}")
        
        # Load optional files
        for key, filename in optional_files.items():
            file_path = path / filename
            if file_path.exists():
                with open(file_path, 'r', encoding='utf-8') as f:
                    snapshot[key] = json.load(f)
                print(f"  ✓ {filename} (optional)")
            else:
                snapshot[key] = None
                print(f"  ⚠ {filename} (optional, not found)")
        
        print()
        return snapshot
    
    def build_url_map(self, snapshot: Dict[str, Any]) -> Dict[str, Dict]:
        """
        Build URL mapping with redirect resolution.
        
        Args:
            snapshot: Snapshot data
            
        Returns:
            Dictionary mapping URLs to combined page data
        """
        url_map = {}
        
        # Index all data by URL
        pages_by_url = {p['url']: p for p in snapshot['pages']}
        indexability_by_url = {p['url']: p for p in snapshot['indexability']}
        priority_by_url = {p['url']: p for p in snapshot['priority']}
        content_by_url = {p['url']: p for p in snapshot['content_quality']}
        canonical_by_url = snapshot['canonical_clusters']
        
        # Build combined data for each URL
        for url in pages_by_url.keys():
            url_map[url] = {
                'page': pages_by_url.get(url, {}),
                'indexability': indexability_by_url.get(url, {}),
                'priority': priority_by_url.get(url, {}),
                'content': content_by_url.get(url, {}),
                'canonical': canonical_by_url.get(url, {}),
            }
        
        return url_map
    
    def calculate_indexability_delta(self, before: Dict, after: Dict) -> float:
        """
        Calculate indexability improvement.
        
        Returns:
            1.0 if became indexable, -1.0 if lost indexability, 0.0 if unchanged
        """
        before_indexable = before.get('indexable', False)
        after_indexable = after.get('indexable', False)
        
        if not before_indexable and after_indexable:
            return 1.0  # Became indexable
        elif before_indexable and not after_indexable:
            return -1.0  # Lost indexability
        else:
            return 0.0  # No change
    
    def calculate_priority_delta(self, before: Dict, after: Dict) -> float:
        """
        Calculate priority score improvement (normalized).
        
        Returns:
            Delta in priority score (-1.0 to 1.0)
        """
        before_score = before.get('priority_score', 0.0)
        after_score = after.get('priority_score', 0.0)
        
        return after_score - before_score
    
    def calculate_quality_delta(self, before: Dict, after: Dict) -> float:
        """
        Calculate content quality improvement (normalized).
        
        Returns:
            Delta in quality score (-1.0 to 1.0)
        """
        before_score = before.get('quality_score', 0.0)
        after_score = after.get('quality_score', 0.0)
        
        return after_score - before_score
    
    def calculate_canonical_fix(self, before: Dict, after: Dict) -> float:
        """
        Check if canonical issue was resolved.
        
        Returns:
            1.0 if fixed, 0.0 if not fixed or no issue
        """
        before_canonical = before.get('canonical_info', {})
        after_canonical = after.get('canonical_info', {})
        
        before_is_leader = before_canonical.get('is_cluster_leader', True)
        after_is_leader = after_canonical.get('is_cluster_leader', True)
        
        # If was not leader but became leader = fixed
        if not before_is_leader and after_is_leader:
            return 1.0
        
        return 0.0
    
    def calculate_impact_score(self, before_data: Dict, after_data: Dict) -> Tuple[float, str]:
        """
        Calculate overall impact score for a page.
        
        Formula:
            impact_score = (
                indexability_delta * 0.35 +
                priority_delta     * 0.30 +
                quality_delta      * 0.20 +
                canonical_fix      * 0.15
            )
        
        Returns:
            Tuple of (impact_score, status)
        """
        indexability_delta = self.calculate_indexability_delta(
            before_data['indexability'],
            after_data['indexability']
        )
        
        priority_delta = self.calculate_priority_delta(
            before_data['priority'],
            after_data['priority']
        )
        
        quality_delta = self.calculate_quality_delta(
            before_data['content'],
            after_data['content']
        )
        
        canonical_fix = self.calculate_canonical_fix(
            before_data['canonical'],
            after_data['canonical']
        )
        
        # Calculate weighted impact score
        impact_score = (
            indexability_delta * 0.35 +
            priority_delta     * 0.30 +
            quality_delta      * 0.20 +
            canonical_fix      * 0.15
        )
        
        # Determine status
        if impact_score > 0.05:
            status = "IMPROVED"
        elif impact_score < -0.05:
            status = "DECLINED"
        else:
            status = "UNCHANGED"
        
        return round(impact_score, 3), status
    
    def compare_pages(self):
        """Compare pages between before and after snapshots."""
        print("Comparing pages...")
        
        # Build URL maps
        before_urls = self.build_url_map(self.before)
        after_urls = self.build_url_map(self.after)
        
        # Find common URLs
        common_urls = set(before_urls.keys()) & set(after_urls.keys())
        new_urls = set(after_urls.keys()) - set(before_urls.keys())
        removed_urls = set(before_urls.keys()) - set(after_urls.keys())
        
        print(f"  Common URLs: {len(common_urls)}")
        print(f"  New URLs: {len(new_urls)}")
        print(f"  Removed URLs: {len(removed_urls)}")
        print()
        
        # Compare common pages
        for url in common_urls:
            before_data = before_urls[url]
            after_data = after_urls[url]
            
            # Calculate impact
            impact_score, status = self.calculate_impact_score(before_data, after_data)
            
            # Build page impact entry
            page_impact = {
                'url': url,
                'before': {
                    'indexable': before_data['indexability'].get('indexable', False),
                    'priority_score': before_data['priority'].get('priority_score', 0.0),
                    'priority_tier': before_data['priority'].get('priority_tier', 'LOW'),
                    'quality_score': before_data['content'].get('quality_score', 0.0),
                    'quality_grade': before_data['content'].get('quality_grade', 'F'),
                    'is_cluster_leader': before_data['canonical'].get('canonical_info', {}).get('is_cluster_leader', True),
                },
                'after': {
                    'indexable': after_data['indexability'].get('indexable', False),
                    'priority_score': after_data['priority'].get('priority_score', 0.0),
                    'priority_tier': after_data['priority'].get('priority_tier', 'LOW'),
                    'quality_score': after_data['content'].get('quality_score', 0.0),
                    'quality_grade': after_data['content'].get('quality_grade', 'F'),
                    'is_cluster_leader': after_data['canonical'].get('canonical_info', {}).get('is_cluster_leader', True),
                },
                'impact_score': impact_score,
                'status': status
            }
            
            self.page_impacts.append(page_impact)
            
            # Identify winners and failures
            if status == "IMPROVED" and impact_score >= 0.2:
                reasons = []
                if page_impact['before']['indexable'] != page_impact['after']['indexable']:
                    reasons.append('indexability_fixed')
                if page_impact['after']['priority_score'] > page_impact['before']['priority_score'] + 0.1:
                    reasons.append('priority_increased')
                if page_impact['after']['quality_score'] > page_impact['before']['quality_score'] + 0.1:
                    reasons.append('quality_improved')
                if not page_impact['before']['is_cluster_leader'] and page_impact['after']['is_cluster_leader']:
                    reasons.append('canonical_resolved')
                
                self.winners.append({
                    'url': url,
                    'reasons': reasons,
                    'net_gain': impact_score
                })
            
            elif status == "DECLINED" or (status == "UNCHANGED" and not page_impact['after']['indexable']):
                issues = []
                if not page_impact['after']['indexable']:
                    issues.append('still_not_indexable')
                if not page_impact['after']['is_cluster_leader']:
                    issues.append('canonical_still_wrong')
                if page_impact['after']['quality_grade'] in ['D', 'F']:
                    issues.append('quality_still_poor')
                
                if issues:
                    self.failures.append({
                        'url': url,
                        'issues': issues,
                        'suggestion': 'manual_review'
                    })
        
        print(f"Analyzed {len(self.page_impacts)} pages")
        print(f"  Winners: {len(self.winners)}")
        print(f"  Failures: {len(self.failures)}")
        print()
    
    def calculate_metrics_delta(self):
        """Calculate module-level metric changes."""
        print("Calculating metrics delta...")
        
        # Indexability metrics
        before_indexable = sum(1 for p in self.before['indexability'] if p.get('indexable', False))
        after_indexable = sum(1 for p in self.after['indexability'] if p.get('indexable', False))
        
        # Priority metrics
        before_priority_avg = sum(p.get('priority_score', 0.0) for p in self.before['priority']) / len(self.before['priority']) if self.before['priority'] else 0
        after_priority_avg = sum(p.get('priority_score', 0.0) for p in self.after['priority']) / len(self.after['priority']) if self.after['priority'] else 0
        
        before_high_priority = sum(1 for p in self.before['priority'] if p.get('priority_tier') in ['CRITICAL', 'HIGH'])
        after_high_priority = sum(1 for p in self.after['priority'] if p.get('priority_tier') in ['CRITICAL', 'HIGH'])
        
        # Quality metrics
        before_quality_avg = sum(p.get('quality_score', 0.0) for p in self.before['content_quality']) / len(self.before['content_quality']) if self.before['content_quality'] else 0
        after_quality_avg = sum(p.get('quality_score', 0.0) for p in self.after['content_quality']) / len(self.after['content_quality']) if self.after['content_quality'] else 0
        
        # Canonical metrics
        before_leaders = sum(1 for url, data in self.before['canonical_clusters'].items() if data.get('canonical_info', {}).get('is_cluster_leader', True))
        after_leaders = sum(1 for url, data in self.after['canonical_clusters'].items() if data.get('canonical_info', {}).get('is_cluster_leader', True))
        
        self.metrics_delta = {
            'indexability': {
                'before': {'indexable': before_indexable},
                'after': {'indexable': after_indexable},
                'delta': after_indexable - before_indexable
            },
            'priority': {
                'avg_score_delta': round(after_priority_avg - before_priority_avg, 3),
                'high_priority_pages_delta': after_high_priority - before_high_priority
            },
            'content_quality': {
                'avg_quality_delta': round(after_quality_avg - before_quality_avg, 3),
                'pages_analyzed': len(self.after['content_quality'])
            },
            'canonical': {
                'cluster_leaders_delta': after_leaders - before_leaders
            }
        }
        
        print("  ✓ Metrics calculated")
        print()
    
    def generate_summary(self):
        """Generate executive summary."""
        print("Generating summary...")
        
        # Calculate overall status
        improved_count = sum(1 for p in self.page_impacts if p['status'] == 'IMPROVED')
        declined_count = sum(1 for p in self.page_impacts if p['status'] == 'DECLINED')
        
        if improved_count > declined_count * 2:
            overall_status = "IMPROVED"
        elif declined_count > improved_count * 2:
            overall_status = "DECLINED"
        else:
            overall_status = "NEUTRAL"
        
        # Calculate confidence score
        total_pages = len(self.page_impacts)
        confidence_score = min(1.0, total_pages / 100)  # Higher confidence with more pages
        
        self.summary = {
            'snapshots': {
                'before': self.before_timestamp,
                'after': self.after_timestamp
            },
            'overall_status': overall_status,
            'pages_compared': total_pages,
            'pages_improved': improved_count,
            'pages_declined': declined_count,
            'pages_unchanged': total_pages - improved_count - declined_count,
            'metrics_delta': {
                'indexable_pages': self.metrics_delta['indexability']['delta'],
                'avg_priority_score': self.metrics_delta['priority']['avg_score_delta'],
                'avg_quality_score': self.metrics_delta['content_quality']['avg_quality_delta'],
                'canonical_leaders': self.metrics_delta['canonical']['cluster_leaders_delta']
            },
            'confidence_score': round(confidence_score, 2),
            'generated_at': datetime.now().isoformat()
        }
        
        print("  ✓ Summary generated")
        print()
    
    def export_results(self):
        """Export all result files."""
        print("Exporting results...")
        
        # 1. Summary
        summary_file = self.output_dir / 'change_impact_summary.json'
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(self.summary, f, indent=2, ensure_ascii=False)
        print(f"  ✓ {summary_file.name}")
        
        # 2. Metrics
        metrics_file = self.output_dir / 'change_impact_metrics.json'
        with open(metrics_file, 'w', encoding='utf-8') as f:
            json.dump(self.metrics_delta, f, indent=2, ensure_ascii=False)
        print(f"  ✓ {metrics_file.name}")
        
        # 3. Pages
        pages_file = self.output_dir / 'change_impact_pages.json'
        with open(pages_file, 'w', encoding='utf-8') as f:
            json.dump(self.page_impacts, f, indent=2, ensure_ascii=False)
        print(f"  ✓ {pages_file.name}")
        
        # 4. Winners
        winners_file = self.output_dir / 'change_impact_winners.json'
        with open(winners_file, 'w', encoding='utf-8') as f:
            json.dump(self.winners, f, indent=2, ensure_ascii=False)
        print(f"  ✓ {winners_file.name}")
        
        # 5. Failures
        failures_file = self.output_dir / 'change_impact_failures.json'
        with open(failures_file, 'w', encoding='utf-8') as f:
            json.dump(self.failures, f, indent=2, ensure_ascii=False)
        print(f"  ✓ {failures_file.name}")
        
        print()
    
    def print_summary(self):
        """Print summary to console."""
        print("=" * 70)
        print("📊 CHANGE IMPACT ANALYSIS COMPLETE")
        print("=" * 70)
        print(f"\nSnapshots:")
        print(f"  Before: {self.summary['snapshots']['before']}")
        print(f"  After:  {self.summary['snapshots']['after']}")
        
        print(f"\nOverall Status: {self.summary['overall_status']}")
        print(f"Confidence Score: {self.summary['confidence_score']}")
        
        print(f"\nPages Compared: {self.summary['pages_compared']}")
        print(f"  ✅ Improved: {self.summary['pages_improved']}")
        print(f"  ❌ Declined: {self.summary['pages_declined']}")
        print(f"  ⚪ Unchanged: {self.summary['pages_unchanged']}")
        
        print(f"\nKey Metrics Delta:")
        print(f"  Indexable Pages: {self.summary['metrics_delta']['indexable_pages']:+d}")
        print(f"  Avg Priority Score: {self.summary['metrics_delta']['avg_priority_score']:+.3f}")
        print(f"  Avg Quality Score: {self.summary['metrics_delta']['avg_quality_score']:+.3f}")
        print(f"  Canonical Leaders: {self.summary['metrics_delta']['canonical_leaders']:+d}")
        
        print(f"\nTop Winners: {len(self.winners)}")
        for winner in self.winners[:5]:
            print(f"  • {winner['url']}")
            print(f"    Gain: {winner['net_gain']:.3f} | Reasons: {', '.join(winner['reasons'])}")
        
        if self.failures:
            print(f"\nIssues Requiring Attention: {len(self.failures)}")
            for failure in self.failures[:5]:
                print(f"  • {failure['url']}")
                print(f"    Issues: {', '.join(failure['issues'])}")
        
        print("\n" + "=" * 70)
        print(f"✨ Results saved to: {self.output_dir}/")
        print("=" * 70 + "\n")
    
    def run(self):
        """Run complete impact analysis."""
        try:
            # Load snapshots
            self.before = self.load_snapshot(self.before_path, "BEFORE")
            self.after = self.load_snapshot(self.after_path, "AFTER")
            
            # Compare pages
            self.compare_pages()
            
            # Calculate metrics
            self.calculate_metrics_delta()
            
            # Generate summary
            self.generate_summary()
            
            # Export results
            self.export_results()
            
            # Print summary
            self.print_summary()
            
            return True
            
        except Exception as e:
            print(f"\n❌ Impact analysis failed: {e}")
            import traceback
            traceback.print_exc()
            return False


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Change Impact Tracker - Validate SEO Progress",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Compare two snapshots
  python change_impact_tracker.py \\
    --before developer_mozilla_org/20260101_101500 \\
    --after developer_mozilla_org/20260107_181502
  
  # Custom output directory
  python change_impact_tracker.py \\
    --before snapshot_A \\
    --after snapshot_B \\
    --output impact_reports/
        """
    )
    
    parser.add_argument(
        '--before',
        required=True,
        help='Path to before snapshot directory'
    )
    
    parser.add_argument(
        '--after',
        required=True,
        help='Path to after snapshot directory'
    )
    
    parser.add_argument(
        '--output',
        default=None,
        help='Output directory for impact reports (default: after_snapshot/impact_analysis/)'
    )
    
    args = parser.parse_args()
    
    # Run impact tracker
    tracker = ChangeImpactTracker(
        snapshot_before=args.before,
        snapshot_after=args.after,
        output_dir=args.output
    )
    
    success = tracker.run()
    
    if not success:
        print("\n❌ Impact analysis failed")
        sys.exit(1)
    
    print("\n✅ Impact analysis completed successfully!")
    sys.exit(0)


if __name__ == "__main__":
    main()
