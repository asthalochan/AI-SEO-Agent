"""
Internal Link Graph Engine (SEO-Grade)
Analyzes crawler output to provide link structure insights for SEO
Includes context weighting, percentile-based hubs, and accurate orphan detection
"""

import json
import math
from typing import Dict, List, Set, Optional
from dataclasses import dataclass, asdict
from pathlib import Path
from collections import defaultdict
from urllib.parse import urlparse
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class LinkNode:
    """Represents a page in the link graph with SEO intelligence"""
    url: str
    normalized_url: str
    inlinks: int = 0
    outlinks: int = 0
    content_inlinks: int = 0  # NEW: Only content-context inlinks
    link_depth: int = 0
    is_orphan: bool = False
    is_hub: bool = False
    is_dead_end: bool = False
    link_score: float = 0.0
    inlink_urls: List[str] = None
    outlink_urls: List[str] = None
    
    # Redirect-aware metrics (CHANGE 2: Store both raw and resolved)
    resolved_outlink_urls: List[str] = None  # NEW: Resolved outlink targets
    raw_outlinks: int = 0
    resolved_outlinks: int = 0
    links_to_redirects: int = 0
    
    def __post_init__(self):
        if self.inlink_urls is None:
            self.inlink_urls = []
        if self.outlink_urls is None:
            self.outlink_urls = []
        if self.resolved_outlink_urls is None:
            self.resolved_outlink_urls = []


class LinkGraphAnalyzer:
    """Analyzes internal link structure with SEO-grade intelligence"""
    
    # Link context weights (SEO-accurate)
    CONTEXT_WEIGHTS = {
        "content": 1.0,
        "breadcrumb": 0.6,
        "nav": 0.3,
        "footer": 0.2
    }
    
    def __init__(self, pages_json_path: str, redirect_map_json_path: Optional[str] = None):
        """
        Initialize analyzer with crawler output
        
        Args:
            pages_json_path: Path to crawler pages JSON file
            redirect_map_json_path: Optional path to redirect_map.json from redirect_resolver
        """
        self.pages_json_path = Path(pages_json_path)
        self.redirect_map_json_path = Path(redirect_map_json_path) if redirect_map_json_path else None
        self.pages_data = self._load_pages()
        self.redirect_map_data = self._load_redirect_map() if self.redirect_map_json_path else None
        self.graph: Dict[str, LinkNode] = {}
        self.url_to_normalized: Dict[str, str] = {}
        self.link_contexts: Dict[tuple, str] = {}  # (source, target) -> context
        self.homepage_url: Optional[str] = None
        self.redirect_map: Dict[str, str] = {}  # NEW: URL -> final_url mapping
        
    def _load_pages(self) -> List[Dict]:
        """Load pages from crawler JSON"""
        with open(self.pages_json_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def _load_redirect_map(self) -> Dict:
        """
        CHANGE 1: Load redirect_map.json as simple URL resolver
        
        Expected format:
        {
          "normalized_source_url": "final_resolved_url",
          ...
        }
        
        ❌ Does NOT store chains, variants, or infer redirects
        ✔️ Redirect map = final authority mapping ONLY
        """
        if not self.redirect_map_json_path or not self.redirect_map_json_path.exists():
            return None
        with open(self.redirect_map_json_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def build_graph(self):
        """Build link graph from crawler data with SEO intelligence"""
        logger.info(f"Building SEO-grade link graph from {len(self.pages_data)} pages...")
        
        # Step 1: Create nodes for all pages
        for page in self.pages_data:
            normalized_url = page['normalized_url']
            
            # Detect homepage
            if self._is_homepage(page):
                self.homepage_url = normalized_url
            
            # Extract outlink URLs (support both old and new format)
            outlinks = page.get('internal_links_filtered', [])
            if outlinks and isinstance(outlinks[0], dict):
                # New format with context
                outlink_urls = [link['url'] for link in outlinks]
            else:
                # Old format (just URLs)
                outlink_urls = outlinks
            
            node = LinkNode(
                url=page['url'],
                normalized_url=normalized_url,
                link_depth=page.get('crawl_depth', 0),
                outlink_urls=outlink_urls
            )
            
            self.graph[normalized_url] = node
            self.url_to_normalized[page['url']] = normalized_url
        
        # Step 2: Build inlink relationships with context tracking (FIXED: exclude self-links)
        for page in self.pages_data:
            source_url = page['normalized_url']
            
            # Get internal links with context
            internal_links = page.get('internal_links', [])
            
            for link in internal_links:
                # Support both old and new format
                if isinstance(link, dict):
                    target_url = link['url']
                    context = link.get('context', 'content')
                else:
                    # Old format (just URL string)
                    target_url = link
                    context = 'content'
                
                # Normalize target URL
                target_normalized = self.url_to_normalized.get(target_url, target_url)
                
                # CRITICAL FIX: Skip self-links
                if target_normalized == source_url:
                    continue
                
                if target_normalized in self.graph:
                    target_node = self.graph[target_normalized]
                    target_node.inlink_urls.append(source_url)
                    
                    # Store link context for weighted PageRank
                    self.link_contexts[(source_url, target_normalized)] = context
                    
                    # Track content inlinks (real data from crawler)
                    if context == 'content':
                        target_node.content_inlinks += 1
        
        # Step 3: Count links
        for node in self.graph.values():
            # Total inlinks (all contexts)
            node.inlinks = len(node.inlink_urls)
            
            # Content inlinks are now tracked from real crawler data
            # No estimation needed!
            
            # Outlinks
            node.outlinks = len(node.outlink_urls)
        
        # Step 3: Load redirect map (if provided)
        if self.redirect_map_data:
            self._build_redirect_map_from_file()
            
            # CHANGE 3: Rebuild inlinks using resolved outlinks (CRITICAL)
            self._apply_redirect_resolution_to_inlinks()
        else:
            # No redirect map provided
            logger.info("⚠️  No redirect_map.json provided — redirect resolution skipped")
            logger.info("   Run redirect_resolver.py first for accurate redirect analysis")
            self.redirect_map = {}
        
        # Step 4: Calculate redirect-aware metrics
        self._calculate_redirect_metrics()
        
        logger.info(f"✓ Link graph built: {len(self.graph)} nodes")
    
    def _is_homepage(self, page: Dict) -> bool:
        """
        Robust homepage detection
        
        Checks:
        1. Crawl depth == 0
        2. URL is / or /index.html
        3. Canonical points to root
        """
        url = page.get('normalized_url', '')
        depth = page.get('crawl_depth', 999)
        canonical = page.get('canonical_url', '')
        
        # Check depth
        if depth == 0:
            return True
        
        # Check URL patterns
        parsed = urlparse(url)
        path = parsed.path.rstrip('/')
        if path in ['', '/index.html', '/index.htm', '/index.php']:
            return True
        
        # Check if canonical points to root
        if canonical:
            canonical_parsed = urlparse(canonical)
            canonical_path = canonical_parsed.path.rstrip('/')
            if canonical_path == '' and parsed.netloc == canonical_parsed.netloc:
                return True
        
        return False
    
    def _estimate_content_inlinks(self, node: LinkNode) -> int:
        """
        Heuristic to estimate content-context inlinks
        Assumes ~40% of inlinks are from nav/footer (conservative)
        
        TODO: Replace with actual context tracking from crawler
        """
        if node.inlinks == 0:
            return 0
        
        # If page has very high inlinks (>80% of total pages), likely in nav
        # Discount heavily
        total_pages = len(self.graph)
        if node.inlinks > total_pages * 0.8:
            return max(1, int(node.inlinks * 0.3))  # Only 30% are content links
        
        # Otherwise assume 60% are content links
        return max(1, int(node.inlinks * 0.6))
    
    def _build_redirect_map_from_file(self):
        """
        CHANGE 1: Build redirect map from redirect_resolver output
        
        Loads simple URL mapping: source -> final
        ❌ Does NOT store chains or metadata
        ✔️ Just the final authority mapping
        """
        logger.info("Loading redirect map from redirect_resolver...")
        
        redirect_count = 0
        for url, record in self.redirect_map_data.items():
            final_url = record.get('final_url')
            if final_url and final_url != url:
                # Simple mapping: source -> final
                self.redirect_map[url] = final_url
                redirect_count += 1
        
        logger.info(f"✓ Redirect map loaded: {redirect_count} redirects")
    
    def _apply_redirect_resolution_to_inlinks(self):
        """
        CHANGE 3: Rebuild inlinks using resolved outlinks (MANDATORY)
        
        This is non-negotiable for SEO correctness.
        Google consolidates inbound links to final URLs after redirects.
        """
        logger.info("Applying redirect resolution to inlinks...")
        
        # Build new inlink mapping using resolved outlink targets
        resolved_inlinks = defaultdict(list)
        
        for source_url, node in self.graph.items():
            # Use resolved_outlink_urls (not raw outlink_urls)
            for final_target in node.resolved_outlink_urls:
                resolved_inlinks[final_target].append(source_url)
        
        # Update all nodes with resolved inlinks
        resolved_count = 0
        for url, node in self.graph.items():
            old_inlinks = len(node.inlink_urls)
            node.inlink_urls = resolved_inlinks.get(url, [])
            node.inlinks = len(node.inlink_urls)
            
            if node.inlinks != old_inlinks:
                resolved_count += 1
        
        logger.info(f"✓ Inlinks resolved: {resolved_count} nodes affected")
    
    def _calculate_redirect_metrics(self):
        """
        CHANGE 2: Calculate redirect-aware metrics
        Stores both raw and resolved outlinks
        """
        logger.info("Calculating redirect-aware metrics...")
        
        for node in self.graph.values():
            # Count raw outlinks
            node.raw_outlinks = len(node.outlink_urls)
            
            # Resolve outlinks and store resolved targets
            resolved_targets = []
            redirect_count = 0
            
            for target_url in node.outlink_urls:
                # Normalize target
                target_normalized = self.url_to_normalized.get(target_url, target_url)
                
                # CHANGE 2: Resolve through redirect map
                final_target = self.redirect_map.get(target_normalized, target_normalized)
                resolved_targets.append(final_target)
                
                # Count if this was a redirect
                if final_target != target_normalized:
                    redirect_count += 1
            
            # CHANGE 2: Store both raw and resolved
            node.resolved_outlink_urls = resolved_targets
            node.resolved_outlinks = len(set(resolved_targets))  # Unique resolved targets
            node.links_to_redirects = redirect_count
        
        logger.info(f"✓ Redirect metrics calculated")
    
    def calculate_metrics(self):
        """Calculate all link metrics"""
        logger.info("Calculating link metrics...")
        
        self.detect_orphans()
        self.detect_hubs()
        self.detect_dead_ends()
        self.calculate_link_scores()
        
        logger.info("✓ Metrics calculated")
    
    def detect_orphans(self):
        """Detect orphan pages (SEO-accurate: uses resolved inlinks)"""
        orphan_count = 0
        
        for node in self.graph.values():
            # Robust homepage detection
            is_homepage = (node.normalized_url == self.homepage_url)
            
            # ISSUE 3 FIX: Use resolved inlinks (after redirect resolution)
            # If redirect map was provided, inlinks are already resolved
            # Otherwise fall back to content_inlinks or total inlinks
            if self.redirect_map:
                # Redirect-aware: use resolved inlinks
                if node.inlinks == 0 and not is_homepage:
                    node.is_orphan = True
                    orphan_count += 1
            else:
                # Fallback: use content_inlinks
                if node.content_inlinks == 0 and not is_homepage:
                    node.is_orphan = True
                    orphan_count += 1
        
        logger.info(f"  → Found {orphan_count} orphan pages (redirect-aware)")
    
    def detect_hubs(self, percentile: float = 95.0):
        """
        Detect link hubs using percentile-based threshold (SEO-accurate)
        
        Args:
            percentile: Percentile threshold (default 95 = top 5%)
        """
        if not self.graph:
            return
        
        # Calculate percentile threshold
        outlink_counts = [node.outlinks for node in self.graph.values()]
        outlink_counts.sort()
        
        threshold_index = int(len(outlink_counts) * (percentile / 100))
        hub_threshold = outlink_counts[threshold_index] if threshold_index < len(outlink_counts) else 50
        
        hub_count = 0
        for node in self.graph.values():
            if node.outlinks >= hub_threshold:
                node.is_hub = True
                hub_count += 1
        
        logger.info(f"  → Found {hub_count} link hubs (top {100-percentile:.0f}%, threshold: {hub_threshold} outlinks)")
    
    def detect_dead_ends(self):
        """Detect dead-end pages (no outlinks)"""
        dead_end_count = 0
        
        for node in self.graph.values():
            if node.outlinks == 0:
                node.is_dead_end = True
                dead_end_count += 1
        
        logger.info(f"  → Found {dead_end_count} dead-end pages")
    
    def calculate_link_scores(self, iterations: int = 10, damping: float = 0.85, use_context_weights: bool = True):
        """
        Calculate link scores using PageRank with optional context weighting
        
        Args:
            iterations: Number of iterations to run
            damping: Damping factor (0.85 is standard)
            use_context_weights: Apply link context weights (nav/footer/content)
        """
        logger.info(f"  → Calculating link scores ({iterations} iterations, weighted={use_context_weights})...")
        
        # Initialize all scores to 1.0
        num_pages = len(self.graph)
        for node in self.graph.values():
            node.link_score = 1.0
        
        # Iterative calculation
        for iteration in range(iterations):
            new_scores = {}
            
            for url, node in self.graph.items():
                # Base score (random surfer)
                score = (1 - damping)
                
                # Add score from inlinks (with optional context weighting)
                for inlink_url in node.inlink_urls:
                    inlink_node = self.graph[inlink_url]
                    
                    # CHANGE 4: Use resolved_outlinks for redirect-aware PageRank
                    outlink_count = inlink_node.resolved_outlinks or inlink_node.outlinks
                    
                    if outlink_count > 0:
                        # Get link context weight
                        if use_context_weights:
                            context = self.link_contexts.get((inlink_url, url), 'content')
                            weight = self.CONTEXT_WEIGHTS.get(context, 1.0)
                        else:
                            weight = 1.0
                        
                        # Weighted PageRank formula (redirect-aware)
                        score += damping * (weight * inlink_node.link_score / outlink_count)
                
                new_scores[url] = score
            
            # Update scores
            for url, score in new_scores.items():
                self.graph[url].link_score = score
        
        # IMPROVED: Log-scaled normalization (preserves ranking differences)
        max_score = max(node.link_score for node in self.graph.values())
        if max_score > 0:
            for node in self.graph.values():
                # Log-scaled normalization
                node.link_score = round(
                    math.log(node.link_score + 1) / math.log(max_score + 1),
                    3
                )
        
        logger.info(f"  ✓ Link scores calculated (log-scaled normalization)")
    
    def get_summary_stats(self) -> Dict:
        """Get summary statistics with SEO insights"""
        orphans = [n for n in self.graph.values() if n.is_orphan]
        hubs = [n for n in self.graph.values() if n.is_hub]
        dead_ends = [n for n in self.graph.values() if n.is_dead_end]
        
        avg_inlinks = sum(n.inlinks for n in self.graph.values()) / len(self.graph)
        avg_content_inlinks = sum(n.content_inlinks for n in self.graph.values()) / len(self.graph)
        avg_outlinks = sum(n.outlinks for n in self.graph.values()) / len(self.graph)
        avg_score = sum(n.link_score for n in self.graph.values()) / len(self.graph)
        
        return {
            "total_pages": len(self.graph),
            "orphan_pages": len(orphans),
            "link_hubs": len(hubs),
            "dead_end_pages": len(dead_ends),
            "avg_inlinks": round(avg_inlinks, 2),
            "avg_content_inlinks": round(avg_content_inlinks, 2),  # NEW
            "avg_outlinks": round(avg_outlinks, 2),
            "avg_link_score": round(avg_score, 3),
            "top_pages_by_inlinks": sorted(
                [(n.url, n.inlinks) for n in self.graph.values()],
                key=lambda x: x[1],
                reverse=True
            )[:10],
            "top_pages_by_content_inlinks": sorted(  # NEW
                [(n.url, n.content_inlinks) for n in self.graph.values()],
                key=lambda x: x[1],
                reverse=True
            )[:10],
            "top_pages_by_score": sorted(
                [(n.url, n.link_score) for n in self.graph.values()],
                key=lambda x: x[1],
                reverse=True
            )[:10]
        }
    
    def export_results(self, output_path: str):
        """Export link graph results to JSON"""
        output_path = Path(output_path)
        
        # Convert graph to list of dicts
        results = [asdict(node) for node in self.graph.values()]
        
        # Add summary stats
        output_data = {
            "summary": self.get_summary_stats(),
            "pages": results
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"✓ Results exported to {output_path}")
        
        return output_data
    
    def analyze(self, output_path: Optional[str] = None) -> Dict:
        """
        Run complete analysis
        
        Args:
            output_path: Optional path to save results
            
        Returns:
            Analysis results
        """
        self.build_graph()
        self.calculate_metrics()
        
        if output_path:
            return self.export_results(output_path)
        
        return {
            "summary": self.get_summary_stats(),
            "pages": [asdict(node) for node in self.graph.values()]
        }


def analyze_link_graph(pages_json_path: str, 
                      redirect_map_json_path: Optional[str] = None,
                      output_path: Optional[str] = None) -> Dict:
    """
    Convenience function to analyze link graph
    
    Args:
        pages_json_path: Path to crawler pages JSON
        redirect_map_json_path: Optional path to redirect_map.json from redirect_resolver
        output_path: Optional path to save results
        
    Returns:
        Analysis results
    """
    analyzer = LinkGraphAnalyzer(pages_json_path, redirect_map_json_path)
    return analyzer.analyze(output_path)


if __name__ == "__main__":
    import sys
    from urllib.parse import urlparse
    
    # Check if path provided via command line
    if len(sys.argv) >= 2:
        pages_json = sys.argv[1]
        redirect_map_json = sys.argv[2] if len(sys.argv) > 2 else None
        output_json = sys.argv[3] if len(sys.argv) > 3 else None
    else:
        # Manual path input
        print("=" * 70)
        print("🔗 LINK GRAPH ANALYZER")
        print("=" * 70)
        print("\nEnter the path to your crawler pages JSON file:")
        print("Example: crawler_output/developer_mozilla_org_20251217_115130_pages.json")
        print()
        
        pages_json = input("Pages JSON path: ").strip()
        
        if not pages_json:
            print("❌ Error: No path provided")
            sys.exit(1)
        
        # Check if file exists
        if not Path(pages_json).exists():
            print(f"❌ Error: File not found: {pages_json}")
            sys.exit(1)
        
        # Ask for redirect map (optional)
        print("\nEnter path to redirect_map.json (optional, press Enter to skip):")
        print("Example: crawler_output/developer_mozilla_org_20251220_054821_pages_redirect_map.json")
        redirect_map_json = input("Redirect map path (optional): ").strip() or None
        
        if redirect_map_json and not Path(redirect_map_json).exists():
            print(f"⚠️  Warning: Redirect map file not found: {redirect_map_json}")
            print("   Continuing without redirect resolution...")
            redirect_map_json = None
        
        # Ask for output path (optional)
        print("\nEnter output path (press Enter to auto-generate):")
        output_json = input("Output path (optional): ").strip()
        
        if not output_json:
            # Auto-generate output path
            input_path = Path(pages_json)
            output_json = str(input_path.parent / f"{input_path.stem}_link_graph.json")
            print(f"✓ Output will be saved to: {output_json}")
    
    print(f"\n🔗 Analyzing link graph from: {pages_json}")
    if redirect_map_json:
        print(f"   Using redirect map: {redirect_map_json}")
    results = analyze_link_graph(pages_json, redirect_map_json, output_json)
    
    # Print summary
    print("\n" + "=" * 70)
    print("📊 LINK GRAPH SUMMARY (SEO-Grade)")
    print("=" * 70)
    summary = results['summary']
    print(f"Total Pages: {summary['total_pages']}")
    print(f"⚠️  Orphan Pages: {summary['orphan_pages']} (content-link basis)")
    print(f"🔗 Link Hubs: {summary['link_hubs']} (percentile-based)")
    print(f"🚫 Dead-End Pages: {summary['dead_end_pages']}")
    print(f"📈 Avg Inlinks: {summary['avg_inlinks']}")
    print(f"📈 Avg Content Inlinks: {summary['avg_content_inlinks']} (SEO-weighted)")
    print(f"📉 Avg Outlinks: {summary['avg_outlinks']}")
    print(f"⭐ Avg Link Score: {summary['avg_link_score']} (log-scaled)")
    print("\n🏆 Top 5 Pages by Link Score:")
    for url, score in summary['top_pages_by_score'][:5]:
        print(f"  {score:.3f} - {url}")
    print("\n🔗 Top 5 Pages by Content Inlinks:")
    for url, count in summary['top_pages_by_content_inlinks'][:5]:
        print(f"  {count} - {url}")
    print("=" * 70)

