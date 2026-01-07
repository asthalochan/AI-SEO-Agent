#!/usr/bin/env python3
"""
Production-Grade SEO Activation Loop

Orchestrates the entire SEO system with organized output structure:
  domain_name/YYYYMMDD_HHMMSS/

Features:
- Clean directory organization per domain and timestamp
- Easy to manage multiple runs of same website
- Easy to manage different websites
- All outputs in one organized location
- CLI support for automation
"""

import json
import sys
import argparse
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse
from typing import Dict, Any

# Import all SEO modules
from crawler import EnterpriseCrawler
from redirect_resolver import RedirectResolver
from link_graph import LinkGraphAnalyzer
from canonical_clusters import CanonicalClusterAnalyzer
from indexability_analyzer import IndexabilityAnalyzer
from content_quality_analyzer import ContentQualityAnalyzer
from page_priority_engine import PagePriorityEngine
from page_experience_analyzer import PageExperienceAnalyzer
from seo_fix_recommendation_engine import SEOFixRecommendationEngine
from execution_plan_generator import ExecutionPlanGenerator


# Constants
TOTAL_MODULES = 10  # Total number of modules in the pipeline
CORE_MODULES = 9    # Core modules (excluding optional Page Experience Analyzer)


class ProductionActivationLoop:
    """
    Production-Grade SEO Activation Loop.
    
    Output structure: domain_name/YYYYMMDD_HHMMSS/
    All files use consistent naming: pages.json, pages_redirect_map.json, etc.
    """
    
    def __init__(self, domain: str, crawl_limit: int = 100):
        """
        Initialize Production Activation Loop.
        
        Args:
            domain: Domain to analyze (e.g., https://example.com)
            crawl_limit: Maximum pages to crawl
        """
        self.domain = domain
        self.crawl_limit = crawl_limit
        
        # Extract clean domain name for folder
        parsed = urlparse(domain)
        self.domain_name = parsed.netloc.replace('www.', '').replace('.', '_')
        
        # Create organized output directory: domain_name/YYYYMMDD_HHMMSS/
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.output_dir = Path(self.domain_name) / self.timestamp
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # File naming strategy: each module uses its own prefix
        # crawler_pages.json, redirect_map.json, link_graph.json, etc.
        self.crawler_base = str(self.output_dir / "crawler")
        
        # Track execution
        self.start_time = datetime.now()
        self.modules_completed = []
        
        print(f"\n📁 Output Directory: {self.output_dir}")
        print(f"📝 Crawler Base: {self.crawler_base}")
    
    def run(self) -> bool:
        """
        Run the complete activation loop.
        
        Returns:
            True if successful
        """
        print("\n" + "=" * 70)
        print("� PRODUCTION SEO ACTIVATION LOOP")
        print("=" * 70)
        print(f"\nDomain: {self.domain}")
        print(f"Crawl Limit: {self.crawl_limit}")
        print(f"Output: {self.output_dir}/")
        print()
        
        try:
            # Module 1: Crawler
            if not self.run_crawler():
                return False
            
            # Module 2: Redirect Resolver
            if not self.run_redirect_resolver():
                return False
            
            # Module 3: Link Graph
            if not self.run_link_graph():
                return False
            
            # Module 4: Canonical Clusters
            if not self.run_canonical_clusters():
                return False
            
            # Module 5: Indexability Analyzer
            if not self.run_indexability_analyzer():
                return False
            
            # Module 6: Content Quality Analyzer
            if not self.run_content_quality_analyzer():
                return False
            
            # Module 7: Page Priority Engine
            if not self.run_page_priority_engine():
                return False
            
            # Module 8: Page Experience Analyzer (optional)
            self.run_page_experience_analyzer()
            
            # Module 9: SEO Fix Recommendation Engine
            if not self.run_seo_fix_engine():
                return False
            
            # Module 10: Execution Plan Generator
            if not self.run_execution_plan_generator():
                return False
            
            # Save metadata
            self.save_metadata()
            
            # Print summary
            self.print_summary()
            
            return True
            
        except Exception as e:
            print(f"\n❌ Activation loop failed: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def run_crawler(self) -> bool:
        """Run crawler module."""
        print("\n" + "=" * 70)
        print("▶ Module 1: Crawler")
        print("=" * 70)
        
        try:
            # Use 'crawler' as base_name
            # Creates: crawler_pages.json, crawler_errors.json, crawler_summary.json
            crawler = EnterpriseCrawler(
                max_pages=self.crawl_limit,
                rate_limit=1.0,
                output_dir=str(self.output_dir),
                base_name="crawler"
            )
            
            crawler.crawl(self.domain)
            
            self.modules_completed.append("crawler")
            print("✅ Crawler completed")
            return True
            
        except Exception as e:
            print(f"❌ Crawler failed: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def run_redirect_resolver(self) -> bool:
        """Run redirect resolver module."""
        print("\n" + "=" * 70)
        print("▶ Module 2: Redirect Resolver")
        print("=" * 70)
        
        try:
            pages_file = str(self.output_dir / "crawler_pages.json")
            
            resolver = RedirectResolver(pages_file)
            resolver.analyze()
            resolver.export_results(str(self.output_dir))
            
            self.modules_completed.append("redirect_resolver")
            print("✅ Redirect Resolver completed")
            return True
            
        except Exception as e:
            print(f"❌ Redirect Resolver failed: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def run_link_graph(self) -> bool:
        """Run link graph module."""
        print("\n" + "=" * 70)
        print("▶ Module 3: Link Graph")
        print("=" * 70)
        
        try:
            pages_file = str(self.output_dir / "crawler_pages.json")
            redirect_file = str(self.output_dir / "crawler_pages_redirect_map.json")
            # PagePriorityEngine expects: crawler_pages_link_graph.json
            output_file = str(self.output_dir / "crawler_pages_link_graph.json")
            
            analyzer = LinkGraphAnalyzer(pages_file, redirect_file)
            analyzer.analyze(output_file)
            
            self.modules_completed.append("link_graph")
            print("✅ Link Graph completed")
            return True
            
        except Exception as e:
            print(f"❌ Link Graph failed: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def run_canonical_clusters(self) -> bool:
        """Run canonical clusters module."""
        print("\n" + "=" * 70)
        print("▶ Module 4: Canonical Clusters")
        print("=" * 70)
        
        try:
            pages_file = str(self.output_dir / "crawler_pages.json")
            link_graph_file = str(self.output_dir / "crawler_pages_link_graph.json")
            # PagePriorityEngine expects: crawler_pages_canonical_clusters_page_index.json
            output_file = str(self.output_dir / "crawler_pages_canonical_clusters.json")
            
            analyzer = CanonicalClusterAnalyzer(pages_file, link_graph_file)
            analyzer.analyze()
            analyzer.export_results(output_file)
            
            self.modules_completed.append("canonical_clusters")
            print("✅ Canonical Clusters completed")
            return True
            
        except Exception as e:
            print(f"❌ Canonical Clusters failed: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def run_indexability_analyzer(self) -> bool:
        """Run indexability analyzer module."""
        print("\n" + "=" * 70)
        print("▶ Module 5: Indexability Analyzer")
        print("=" * 70)
        
        try:
            # IndexabilityAnalyzer expects full path to pages file
            pages_file = str(self.output_dir / "crawler_pages.json")
            
            analyzer = IndexabilityAnalyzer(pages_file)
            analyzer.run()
            
            self.modules_completed.append("indexability_analyzer")
            print("✅ Indexability Analyzer completed")
            return True
            
        except Exception as e:
            print(f"❌ Indexability Analyzer failed: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def run_content_quality_analyzer(self) -> bool:
        """Run content quality analyzer module."""
        print("\n" + "=" * 70)
        print("▶ Module 6: Content Quality Analyzer")
        print("=" * 70)
        
        try:
            pages_file = str(self.output_dir / "crawler_pages.json")
            
            analyzer = ContentQualityAnalyzer(pages_file)
            analyzer.run()
            
            self.modules_completed.append("content_quality_analyzer")
            print("✅ Content Quality Analyzer completed")
            return True
            
        except Exception as e:
            print(f"❌ Content Quality Analyzer failed: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def run_page_priority_engine(self) -> bool:
        """Run page priority engine module."""
        print("\n" + "=" * 70)
        print("▶ Module 7: Page Priority Engine")
        print("=" * 70)
        
        try:
            # PagePriorityEngine expects base_path (without _pages.json)
            base_path = str(self.output_dir / "crawler")
            
            engine = PagePriorityEngine(base_path)
            engine.run()
            
            self.modules_completed.append("page_priority_engine")
            print("✅ Page Priority Engine completed")
            return True
            
        except Exception as e:
            print(f"❌ Page Priority Engine failed: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def run_page_experience_analyzer(self) -> bool:
        """Run page experience analyzer module (OPTIONAL - External Signal)."""
        print("\n" + "=" * 70)
        print("▶ Module 8: Page Experience Analyzer (OPTIONAL - External Signal)")
        print("=" * 70)
        print("⚠️  Note: This module provides external performance signals")
        print("   It does not block the pipeline if it fails")
        print()
        
        try:
            pages_file = str(self.output_dir / "crawler_pages.json")
            
            analyzer = PageExperienceAnalyzer(pages_file)
            analyzer.run()
            
            self.modules_completed.append("page_experience_analyzer")
            print("✅ Page Experience Analyzer completed")
            return True
            
        except Exception as e:
            print(f"⚠️  Page Experience Analyzer failed (optional, continuing): {e}")
            return True  # Continue even if it fails - this is optional
    
    def run_seo_fix_engine(self) -> bool:
        """Run SEO fix recommendation engine module."""
        print("\n" + "=" * 70)
        print("▶ Module 9: SEO Fix Recommendation Engine")
        print("=" * 70)
        
        try:
            # SEOFixRecommendationEngine expects base_path
            base_path = str(self.output_dir / "crawler")
            
            engine = SEOFixRecommendationEngine(base_path)
            engine.run()
            
            self.modules_completed.append("seo_fix_engine")
            print("✅ SEO Fix Recommendation Engine completed")
            return True
            
        except Exception as e:
            print(f"❌ SEO Fix Recommendation Engine failed: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def run_execution_plan_generator(self) -> bool:
        """Run execution plan generator module."""
        print("\n" + "=" * 70)
        print("▶ Module 10: Execution Plan Generator")
        print("=" * 70)
        
        try:
            # ExecutionPlanGenerator expects base_path
            base_path = str(self.output_dir / "crawler")
            
            generator = ExecutionPlanGenerator(base_path)
            generator.run()
            
            self.modules_completed.append("execution_plan_generator")
            print("✅ Execution Plan Generator completed")
            return True
            
        except Exception as e:
            print(f"❌ Execution Plan Generator failed: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def save_metadata(self):
        """Save activation loop metadata."""
        metadata = {
            "domain": self.domain,
            "domain_name": self.domain_name,
            "timestamp": self.timestamp,
            "crawl_limit": self.crawl_limit,
            "output_directory": str(self.output_dir),
            "started_at": self.start_time.isoformat(),
            "completed_at": datetime.now().isoformat(),
            "execution_time_seconds": (datetime.now() - self.start_time).total_seconds(),
            "modules_completed": self.modules_completed,
            "total_modules": len(self.modules_completed),
            "system_version": "1.0-production"
        }
        
        metadata_file = self.output_dir / "activation_metadata.json"
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
        
        print(f"\n  ✓ Saved activation_metadata.json")
    
    def print_summary(self):
        """Print execution summary."""
        elapsed = (datetime.now() - self.start_time).total_seconds()
        
        print("\n" + "=" * 70)
        print("🎉 ACTIVATION LOOP COMPLETE")
        print("=" * 70)
        print(f"\nDomain: {self.domain}")
        print(f"Output: {self.output_dir}/")
        print(f"Modules Completed: {len(self.modules_completed)}/{TOTAL_MODULES}")
        print(f"  Core Modules: {min(len(self.modules_completed), CORE_MODULES)}/{CORE_MODULES}")
        print(f"Execution Time: {elapsed:.1f}s ({elapsed/60:.1f}m)")
        
        print(f"\n✅ Completed Modules:")
        for i, module in enumerate(self.modules_completed, 1):
            # Mark optional modules
            optional_marker = " (optional)" if module == "page_experience_analyzer" else ""
            print(f"  {i}. {module}{optional_marker}")
        
        print(f"\n📊 Output Files:")
        output_files = sorted(self.output_dir.glob("*.json"))
        for file in output_files:
            size_kb = file.stat().st_size / 1024
            print(f"  • {file.name} ({size_kb:.1f} KB)")
        
        print("\n" + "=" * 70)
        print(f"✨ All outputs saved to: {self.output_dir}/")
        print("=" * 70 + "\n")


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Production-Grade SEO Activation Loop",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Interactive mode (default)
  python activation_loop.py
  
  # Automated mode with CLI arguments
  python activation_loop.py --domain https://example.com --limit 100 --yes
  
  # Custom crawl limit
  python activation_loop.py --domain https://example.com --limit 50
        """
    )
    
    parser.add_argument(
        '--domain',
        type=str,
        help='Domain to analyze (e.g., https://example.com)'
    )
    
    parser.add_argument(
        '--limit',
        type=int,
        default=100,
        help='Maximum pages to crawl (default: 100)'
    )
    
    parser.add_argument(
        '--yes', '-y',
        action='store_true',
        help='Skip confirmation prompt (for automation)'
    )
    
    return parser.parse_args()


def main():
    """Main entry point with CLI support."""
    args = parse_args()
    
    # If domain provided via CLI, use automated mode
    if args.domain:
        domain = args.domain
        crawl_limit = args.limit
        auto_confirm = args.yes
        
        print("=" * 70)
        print("🚀 PRODUCTION SEO ACTIVATION LOOP (CLI Mode)")
        print("=" * 70)
        print(f"\nDomain: {domain}")
        print(f"Crawl Limit: {crawl_limit}")
        print()
        
        if not auto_confirm:
            confirm = input("Start activation loop? (y/n): ").strip().lower()
            if confirm != 'y':
                print("Cancelled.")
                sys.exit(0)
    
    # Otherwise, use interactive mode
    else:
        print("=" * 70)
        print("🚀 PRODUCTION SEO ACTIVATION LOOP")
        print("=" * 70)
        print()
        print("Organized output structure: domain_name/YYYYMMDD_HHMMSS/")
        print()
        
        # Get domain
        print("Enter the domain to analyze:")
        print("Example: https://developer.mozilla.org")
        print()
        domain = input("Domain: ").strip()
        
        if not domain:
            print("❌ Error: Domain is required")
            sys.exit(1)
        
        # Get crawl limit
        print()
        print("Enter maximum pages to crawl (default: 100):")
        print()
        crawl_limit_input = input("Crawl limit: ").strip()
        crawl_limit = int(crawl_limit_input) if crawl_limit_input else 100
        
        print()
        print("=" * 70)
        print("Configuration:")
        print("=" * 70)
        print(f"Domain: {domain}")
        print(f"Crawl Limit: {crawl_limit}")
        print()
        
        # Confirm
        confirm = input("Start activation loop? (y/n): ").strip().lower()
        if confirm != 'y':
            print("Cancelled.")
            sys.exit(0)
    
    # Run activation loop
    loop = ProductionActivationLoop(domain=domain, crawl_limit=crawl_limit)
    success = loop.run()
    
    if not success:
        print("\n❌ Activation loop failed")
        sys.exit(1)
    
    print("\n✅ Activation loop completed successfully!")
    sys.exit(0)


if __name__ == "__main__":
    main()
