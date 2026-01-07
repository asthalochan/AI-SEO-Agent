#!/usr/bin/env python3
"""
Page Experience Analyzer

Evaluates Core Web Vitals and performance metrics to determine if pages are 
fast and stable enough to rank well.

Answers: "Is this page fast and stable enough to rank well?"

This module ONLY evaluates experience signals. It does NOT crawl, discover URLs, 
or modify SEO logic.
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from collections import defaultdict


# Core Web Vitals Thresholds (Google's official thresholds)
LCP_THRESHOLDS = {'good': 2500, 'needs_improvement': 4000}  # ms
CLS_THRESHOLDS = {'good': 0.1, 'needs_improvement': 0.25}   # score
INP_THRESHOLDS = {'good': 200, 'needs_improvement': 500}    # ms
TTFB_THRESHOLDS = {'good': 800, 'needs_improvement': 1800}  # ms

# Experience Grade Thresholds
GRADE_THRESHOLDS = {
    'A': 0.85,
    'B': 0.70,
    'C': 0.55
}


class PageExperienceAnalyzer:
    """
    Page Experience Analyzer - Evaluates Core Web Vitals and performance.
    
    Evaluates:
    - Core Web Vitals (LCP, CLS, INP)
    - Supporting metrics (TTFB, page weight, resource count)
    - Speed score (normalized 0-1)
    - Experience grade (A/B/C/D)
    """
    
    def __init__(self, pages_path: str):
        """
        Initialize Page Experience Analyzer.
        
        Args:
            pages_path: Path to pages.json from crawler
        """
        self.pages_path = pages_path
        self.base_path = str(Path(pages_path).parent / Path(pages_path).stem.replace('_pages', ''))
        self.output_dir = Path(pages_path).parent
        
        # Data storage
        self.pages = []
        self.page_experiences = []
        self.issues = []
    
    def load_pages(self):
        """Load pages from crawler output."""
        print("Loading pages...\n")
        
        print(f"  ✓ Loading {Path(self.pages_path).name}")
        try:
            with open(self.pages_path, 'r', encoding='utf-8') as f:
                self.pages = json.load(f)
            print(f"    Loaded {len(self.pages)} pages")
        except FileNotFoundError:
            print(f"    ✗ Error: {Path(self.pages_path).name} not found")
            raise
        
        print("\nData loading complete.\n")
    
    def normalize_metric_score(self, value: float, good_threshold: float, poor_threshold: float, lower_is_better: bool = True) -> float:
        """
        Normalize a metric to 0-1 score.
        
        Args:
            value: Metric value
            good_threshold: Good threshold
            poor_threshold: Poor threshold
            lower_is_better: If True, lower values are better
            
        Returns:
            Normalized score (0-1)
        """
        if value is None:
            return 0.5  # Neutral score for missing data
        
        if lower_is_better:
            # Lower is better (LCP, INP, TTFB)
            if value <= good_threshold:
                return 1.0
            elif value >= poor_threshold:
                return 0.0
            else:
                # Linear interpolation
                return 1.0 - ((value - good_threshold) / (poor_threshold - good_threshold))
        else:
            # Higher is better (CLS is inverted - lower is better, so this branch is for future metrics)
            if value >= good_threshold:
                return 1.0
            elif value <= poor_threshold:
                return 0.0
            else:
                return (value - poor_threshold) / (good_threshold - poor_threshold)
    
    def classify_metric(self, value: float, good_threshold: float, needs_improvement_threshold: float, lower_is_better: bool = True) -> str:
        """
        Classify a metric as good/needs_improvement/poor.
        
        Args:
            value: Metric value
            good_threshold: Good threshold
            needs_improvement_threshold: Needs improvement threshold
            lower_is_better: If True, lower values are better
            
        Returns:
            Classification (good/needs_improvement/poor)
        """
        if value is None:
            return 'unknown'
        
        if lower_is_better:
            if value <= good_threshold:
                return 'good'
            elif value <= needs_improvement_threshold:
                return 'needs_improvement'
            else:
                return 'poor'
        else:
            if value >= good_threshold:
                return 'good'
            elif value >= needs_improvement_threshold:
                return 'needs_improvement'
            else:
                return 'poor'
    
    def calculate_speed_score(self, lcp: Optional[float], cls: Optional[float], inp: Optional[float], ttfb: Optional[float]) -> float:
        """
        Calculate overall speed score.
        
        Formula: (lcp_score * 0.4) + (cls_score * 0.2) + (inp_score * 0.2) + (ttfb_score * 0.2)
        
        Args:
            lcp: LCP in ms
            cls: CLS score
            inp: INP in ms
            ttfb: TTFB in ms
            
        Returns:
            Speed score (0-1)
        """
        # Normalize each metric
        lcp_score = self.normalize_metric_score(lcp, LCP_THRESHOLDS['good'], LCP_THRESHOLDS['needs_improvement'])
        cls_score = self.normalize_metric_score(cls, CLS_THRESHOLDS['good'], CLS_THRESHOLDS['needs_improvement'])
        inp_score = self.normalize_metric_score(inp, INP_THRESHOLDS['good'], INP_THRESHOLDS['needs_improvement'])
        ttfb_score = self.normalize_metric_score(ttfb, TTFB_THRESHOLDS['good'], TTFB_THRESHOLDS['needs_improvement'])
        
        # Weighted average
        speed_score = (lcp_score * 0.4) + (cls_score * 0.2) + (inp_score * 0.2) + (ttfb_score * 0.2)
        
        return round(speed_score, 3)
    
    def determine_experience_grade(self, speed_score: float) -> str:
        """
        Determine experience grade from speed score.
        
        Args:
            speed_score: Speed score (0-1)
            
        Returns:
            Grade (A/B/C/D)
        """
        if speed_score >= GRADE_THRESHOLDS['A']:
            return 'A'
        elif speed_score >= GRADE_THRESHOLDS['B']:
            return 'B'
        elif speed_score >= GRADE_THRESHOLDS['C']:
            return 'C'
        else:
            return 'D'
    
    def detect_issues(self, page: Dict, lcp: Optional[float], cls: Optional[float], inp: Optional[float], ttfb: Optional[float]) -> List[str]:
        """
        Detect performance issues.
        
        Args:
            page: Page data
            lcp: LCP in ms
            cls: CLS score
            inp: INP in ms
            ttfb: TTFB in ms
            
        Returns:
            List of issues
        """
        issues = []
        
        # LCP issues
        if lcp:
            if lcp > LCP_THRESHOLDS['needs_improvement']:
                issues.append('Poor LCP (> 4000ms)')
            elif lcp > LCP_THRESHOLDS['good']:
                issues.append('LCP slightly above ideal (> 2500ms)')
        
        # CLS issues
        if cls:
            if cls > CLS_THRESHOLDS['needs_improvement']:
                issues.append('Poor CLS (> 0.25)')
            elif cls > CLS_THRESHOLDS['good']:
                issues.append('CLS slightly above ideal (> 0.1)')
        
        # INP issues
        if inp:
            if inp > INP_THRESHOLDS['needs_improvement']:
                issues.append('Poor INP (> 500ms)')
            elif inp > INP_THRESHOLDS['good']:
                issues.append('INP slightly above ideal (> 200ms)')
        
        # TTFB issues
        if ttfb:
            if ttfb > TTFB_THRESHOLDS['needs_improvement']:
                issues.append('Very slow server response (> 1800ms)')
            elif ttfb > TTFB_THRESHOLDS['good']:
                issues.append('Slow server response (> 800ms)')
        
        return issues
    
    def determine_data_source(self, lcp: Optional[float], cls: Optional[float], inp: Optional[float], ttfb: Optional[float]) -> str:
        """IMPROVEMENT 1: Determine data source/confidence.
        
        Args:
            lcp, cls, inp, ttfb: Metric values
            
        Returns:
            Data source (real/estimated/missing)
        """
        metrics_present = sum([lcp is not None, cls is not None, inp is not None, ttfb is not None])
        
        if metrics_present >= 3:
            return 'real'
        elif metrics_present >= 1:
            return 'estimated'
        else:
            return 'missing'
    
    def determine_experience_status(self, lcp: Optional[float], cls: Optional[float], inp: Optional[float], data_source: str) -> str:
        """IMPROVEMENT 3: Determine experience status (separate from risk).
        
        Args:
            lcp, cls, inp: Core Web Vitals
            data_source: Data source type
            
        Returns:
            Status (good/needs_improvement/poor/unknown)
        """
        # If no data, status is unknown
        if data_source == 'missing':
            return 'unknown'
        
        # Count poor metrics
        poor_count = 0
        good_count = 0
        
        if lcp is not None:
            if lcp > LCP_THRESHOLDS['needs_improvement']:
                poor_count += 1
            elif lcp <= LCP_THRESHOLDS['good']:
                good_count += 1
        
        if cls is not None:
            if cls > CLS_THRESHOLDS['needs_improvement']:
                poor_count += 1
            elif cls <= CLS_THRESHOLDS['good']:
                good_count += 1
        
        if inp is not None:
            if inp > INP_THRESHOLDS['needs_improvement']:
                poor_count += 1
            elif inp <= INP_THRESHOLDS['good']:
                good_count += 1
        
        # Determine status
        if poor_count >= 2:
            return 'poor'
        elif poor_count >= 1:
            return 'needs_improvement'
        elif good_count >= 2:
            return 'good'
        else:
            return 'needs_improvement'
    
    def determine_experience_risk(self, experience_status: str, data_source: str, speed_score: float) -> str:
        """IMPROVEMENT 3: Determine experience risk (separate from status).
        
        Args:
            experience_status: Experience status
            data_source: Data source type
            speed_score: Speed score
            
        Returns:
            Risk level (high/medium/low)
        """
        # Unknown data = medium risk (not high, not low)
        if data_source == 'missing':
            return 'medium'
        
        # Poor status = high risk
        if experience_status == 'poor':
            return 'high'
        
        # Good status = low risk
        if experience_status == 'good':
            return 'low'
        
        # Needs improvement = medium risk
        return 'medium'
    
    def analyze_page(self, page: Dict) -> Dict:
        """
        Analyze a single page's experience.
        
        Args:
            page: Page data
            
        Returns:
            Page experience data
        """
        url = page.get('url', '')
        
        # Extract performance metrics (from crawler or default to None)
        performance = page.get('performance', {})
        lcp = performance.get('lcp_ms')
        cls = performance.get('cls')
        inp = performance.get('inp_ms')
        ttfb = performance.get('ttfb_ms')
        page_weight = performance.get('page_weight_kb')
        resource_count = performance.get('resource_count')
        image_weight = performance.get('image_weight_kb')
        
        # IMPROVEMENT 1: Determine data source
        data_source = self.determine_data_source(lcp, cls, inp, ttfb)
        
        # IMPROVEMENT 2: Improved fallback logic
        # Only calculate speed score if we have some data
        if data_source == 'missing':
            speed_score = None
            experience_grade = 'unknown'
        else:
            speed_score = self.calculate_speed_score(lcp, cls, inp, ttfb)
            experience_grade = self.determine_experience_grade(speed_score)
        
        # IMPROVEMENT 3: Determine experience status (not just grade)
        experience_status = self.determine_experience_status(lcp, cls, inp, data_source)
        
        # IMPROVEMENT 3: Determine experience risk
        experience_risk = self.determine_experience_risk(experience_status, data_source, speed_score or 0.5)
        
        # Detect issues
        issues = self.detect_issues(page, lcp, cls, inp, ttfb)
        
        # Classify as poor experience (only if we have data)
        is_poor_experience = experience_status == 'poor'
        
        # Classify each Core Web Vital
        lcp_classification = self.classify_metric(lcp, LCP_THRESHOLDS['good'], LCP_THRESHOLDS['needs_improvement']) if lcp else 'unknown'
        cls_classification = self.classify_metric(cls, CLS_THRESHOLDS['good'], CLS_THRESHOLDS['needs_improvement']) if cls else 'unknown'
        inp_classification = self.classify_metric(inp, INP_THRESHOLDS['good'], INP_THRESHOLDS['needs_improvement']) if inp else 'unknown'
        
        # IMPROVEMENT 4: Mobile context
        mobile_experience_assumed = True  # Future: can be toggled based on device type
        
        return {
            'url': url,
            'lcp_ms': lcp,
            'lcp_classification': lcp_classification,
            'cls': cls,
            'cls_classification': cls_classification,
            'inp_ms': inp,
            'inp_classification': inp_classification,
            'ttfb_ms': ttfb,
            'page_weight_kb': page_weight,
            'resource_count': resource_count,
            'image_weight_kb': image_weight,
            'speed_score': speed_score,
            'experience_grade': experience_grade,
            'experience_status': experience_status,
            'experience_risk': experience_risk,
            'is_poor_experience': is_poor_experience,
            'data_source': data_source,
            'mobile_experience_assumed': mobile_experience_assumed,
            'issues': issues
        }
    
    def analyze(self):
        """Analyze all pages."""
        print("Analyzing page experience...\n")
        
        for page in self.pages:
            experience = self.analyze_page(page)
            self.page_experiences.append(experience)
        
        print(f"Analyzed {len(self.page_experiences)} pages\n")
    
    def generate_issues(self):
        """Generate aggregated issues."""
        print("Generating issues...\n")
        
        # Track issues by type
        issue_tracker = defaultdict(lambda: {'pages': [], 'severity': 'medium'})
        
        for exp in self.page_experiences:
            url = exp['url']
            
            # LCP issues
            if exp['lcp_classification'] == 'poor':
                issue_tracker['poor_lcp']['pages'].append(url)
                issue_tracker['poor_lcp']['severity'] = 'high'
            
            # CLS issues
            if exp['cls_classification'] == 'poor':
                issue_tracker['poor_cls']['pages'].append(url)
                issue_tracker['poor_cls']['severity'] = 'high'
            
            # INP issues
            if exp['inp_classification'] == 'poor':
                issue_tracker['poor_inp']['pages'].append(url)
                issue_tracker['poor_inp']['severity'] = 'high'
            
            # Speed score issues (only if we have a score)
            if exp['speed_score'] is not None and exp['speed_score'] < GRADE_THRESHOLDS['C']:
                issue_tracker['poor_speed']['pages'].append(url)
                issue_tracker['poor_speed']['severity'] = 'high'
            
            # TTFB issues
            if exp['ttfb_ms'] and exp['ttfb_ms'] > TTFB_THRESHOLDS['good']:
                issue_tracker['slow_ttfb']['pages'].append(url)
                issue_tracker['slow_ttfb']['severity'] = 'medium'
        
        # Create issue objects
        issue_definitions = {
            'poor_lcp': {
                'issue_id': 'PE_001',
                'title': 'Poor Largest Contentful Paint (LCP)',
                'threshold': '> 4000ms',
                'recommendation': 'Optimize hero images, enable caching, reduce server response time, use CDN'
            },
            'poor_cls': {
                'issue_id': 'PE_002',
                'title': 'Poor Cumulative Layout Shift (CLS)',
                'threshold': '> 0.25',
                'recommendation': 'Set image dimensions, reserve ad space, avoid inserting content above existing content'
            },
            'poor_inp': {
                'issue_id': 'PE_003',
                'title': 'Poor Interaction to Next Paint (INP)',
                'threshold': '> 500ms',
                'recommendation': 'Reduce JavaScript execution time, optimize event handlers, break up long tasks'
            },
            'poor_speed': {
                'issue_id': 'PE_004',
                'title': 'Poor Overall Speed Score',
                'threshold': '< 0.55',
                'recommendation': 'Address Core Web Vitals issues, optimize resources, improve server performance'
            },
            'slow_ttfb': {
                'issue_id': 'PE_005',
                'title': 'Slow Time to First Byte (TTFB)',
                'threshold': '> 800ms',
                'recommendation': 'Optimize server processing, enable caching, use CDN, upgrade hosting'
            }
        }
        
        for issue_type, data in issue_tracker.items():
            if data['pages']:
                definition = issue_definitions.get(issue_type, {})
                self.issues.append({
                    'issue_id': definition.get('issue_id', 'PE_000'),
                    'severity': data['severity'],
                    'title': definition.get('title', issue_type),
                    'affected_pages': len(data['pages']),
                    'threshold': definition.get('threshold', ''),
                    'recommendation': definition.get('recommendation', '')
                })
        
        print(f"Generated {len(self.issues)} issue types\n")
    
    def generate_summary(self) -> Dict:
        """Generate executive summary."""
        total_pages = len(self.page_experiences)
        
        # IMPROVEMENT 1: Data coverage tracking
        data_coverage = {
            'real_metrics_pages': sum(1 for exp in self.page_experiences if exp['data_source'] == 'real'),
            'estimated_pages': sum(1 for exp in self.page_experiences if exp['data_source'] == 'estimated'),
            'missing_pages': sum(1 for exp in self.page_experiences if exp['data_source'] == 'missing')
        }
        
        # Count by experience status (not grade)
        status_counts = {
            'good': sum(1 for exp in self.page_experiences if exp['experience_status'] == 'good'),
            'needs_improvement': sum(1 for exp in self.page_experiences if exp['experience_status'] == 'needs_improvement'),
            'poor': sum(1 for exp in self.page_experiences if exp['experience_status'] == 'poor'),
            'unknown': sum(1 for exp in self.page_experiences if exp['experience_status'] == 'unknown')
        }
        
        # Count by experience grade (for backward compatibility)
        good_pages = sum(1 for exp in self.page_experiences if exp['experience_grade'] in ['A', 'B'])
        needs_improvement = sum(1 for exp in self.page_experiences if exp['experience_grade'] == 'C')
        poor_pages = sum(1 for exp in self.page_experiences if exp['experience_grade'] == 'D')
        unknown_pages = sum(1 for exp in self.page_experiences if exp['experience_grade'] == 'unknown')
        
        # Average speed score (only for pages with data)
        speed_scores = [exp['speed_score'] for exp in self.page_experiences if exp['speed_score'] is not None]
        avg_speed_score = sum(speed_scores) / len(speed_scores) if speed_scores else None
        
        # Core Web Vitals breakdown
        cwv = {
            'lcp': {'good': 0, 'needs_improvement': 0, 'poor': 0, 'unknown': 0},
            'cls': {'good': 0, 'needs_improvement': 0, 'poor': 0, 'unknown': 0},
            'inp': {'good': 0, 'needs_improvement': 0, 'poor': 0, 'unknown': 0}
        }
        
        for exp in self.page_experiences:
            cwv['lcp'][exp['lcp_classification']] += 1
            cwv['cls'][exp['cls_classification']] += 1
            cwv['inp'][exp['inp_classification']] += 1
        
        return {
            'total_pages': total_pages,
            'data_coverage': data_coverage,
            'experience_status': status_counts,
            'good_pages': good_pages,
            'needs_improvement': needs_improvement,
            'poor_pages': poor_pages,
            'unknown_pages': unknown_pages,
            'avg_speed_score': round(avg_speed_score, 3) if avg_speed_score is not None else None,
            'core_web_vitals': cwv
        }
    
    def export_results(self):
        """Export all results."""
        print("Exporting results...\n")
        
        # 1. Page experience pages
        pages_file = self.output_dir / f"{Path(self.base_path).name}_page_experience_pages.json"
        with open(pages_file, 'w', encoding='utf-8') as f:
            json.dump(self.page_experiences, f, indent=2, ensure_ascii=False)
        print(f"  ✓ {pages_file.name}")
        
        # 2. Page experience issues
        issues_file = self.output_dir / f"{Path(self.base_path).name}_page_experience_issues.json"
        with open(issues_file, 'w', encoding='utf-8') as f:
            json.dump(self.issues, f, indent=2, ensure_ascii=False)
        print(f"  ✓ {issues_file.name}")
        
        # 3. Page experience summary
        summary = self.generate_summary()
        summary_file = self.output_dir / f"{Path(self.base_path).name}_page_experience_summary.json"
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        print(f"  ✓ {summary_file.name}")
        
        # Print summary
        print("\n" + "=" * 70)
        print("⚡ PAGE EXPERIENCE ANALYZER COMPLETE")
        print("=" * 70)
        print(f"\n  Total Pages: {summary['total_pages']}")
        
        # IMPROVEMENT 1: Show data coverage
        print(f"\n  Data Coverage:")
        print(f"    Real metrics: {summary['data_coverage']['real_metrics_pages']} pages")
        print(f"    Estimated: {summary['data_coverage']['estimated_pages']} pages")
        print(f"    Missing: {summary['data_coverage']['missing_pages']} pages")
        
        # IMPROVEMENT 3: Show experience status
        print(f"\n  Experience Status:")
        print(f"    Good: {summary['experience_status']['good']}")
        print(f"    Needs Improvement: {summary['experience_status']['needs_improvement']}")
        print(f"    Poor: {summary['experience_status']['poor']}")
        print(f"    Unknown: {summary['experience_status']['unknown']}")
        
        print(f"\n  Experience Grades:")
        print(f"    A/B (Good): {summary['good_pages']}")
        print(f"    C (Needs Improvement): {summary['needs_improvement']}")
        print(f"    D (Poor): {summary['poor_pages']}")
        print(f"    Unknown: {summary['unknown_pages']}")
        
        if summary['avg_speed_score'] is not None:
            print(f"\n  Average Speed Score: {summary['avg_speed_score']}")
        else:
            print(f"\n  Average Speed Score: N/A (no data)")
        
        print(f"\n  Core Web Vitals:")
        print(f"    LCP - Good: {summary['core_web_vitals']['lcp']['good']}, "
              f"NI: {summary['core_web_vitals']['lcp']['needs_improvement']}, "
              f"Poor: {summary['core_web_vitals']['lcp']['poor']}, "
              f"Unknown: {summary['core_web_vitals']['lcp']['unknown']}")
        print(f"    CLS - Good: {summary['core_web_vitals']['cls']['good']}, "
              f"NI: {summary['core_web_vitals']['cls']['needs_improvement']}, "
              f"Poor: {summary['core_web_vitals']['cls']['poor']}, "
              f"Unknown: {summary['core_web_vitals']['cls']['unknown']}")
        print(f"    INP - Good: {summary['core_web_vitals']['inp']['good']}, "
              f"NI: {summary['core_web_vitals']['inp']['needs_improvement']}, "
              f"Poor: {summary['core_web_vitals']['inp']['poor']}, "
              f"Unknown: {summary['core_web_vitals']['inp']['unknown']}")
        
        print(f"\n  Issues Detected: {len(self.issues)}")
        
        print("\n" + "=" * 70 + "\n")
    
    def run(self):
        """Run the complete page experience analysis."""
        self.load_pages()
        self.analyze()
        self.generate_issues()
        self.export_results()


def main():
    """Main entry point."""
    print("=" * 70)
    print("⚡ PAGE EXPERIENCE ANALYZER")
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
    
    # Check if file exists
    if not os.path.exists(pages_path):
        print(f"Error: File not found: {pages_path}")
        return
    
    print()
    print("=" * 70)
    print("⚡ PAGE EXPERIENCE ANALYZER")
    print("=" * 70)
    print()
    
    # Run analyzer
    analyzer = PageExperienceAnalyzer(pages_path)
    analyzer.run()


if __name__ == "__main__":
    main()
