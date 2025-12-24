
"""
Indexability & Crawl Budget Analyzer

Answers Google's three critical questions:
1. Can I crawl this URL?
2. Should I index this URL?
3. Am I wasting crawl budget on it?

This module integrates redirect resolution, canonical clustering, and link graph data
to provide strategic SEO insights and actionable recommendations.
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Set, Optional, Tuple
from collections import defaultdict
from urllib.parse import urlparse, parse_qs


# Configuration
CONFIG = {
    "min_word_count": 100,
    "thin_content_threshold": 150,
    "utility_page_types": ["auth", "utility", "error"],
    "issue_severity_thresholds": {
        "critical": 100,
        "high": 50,
        "medium": 20,
        "low": 10
    }
}


class IndexabilityAnalyzer:
    """Main analyzer class for indexability and crawl budget analysis."""
    
    def __init__(self, pages_file: str, output_dir: Optional[str] = None):
        """
        Initialize the analyzer.
        
        Args:
            pages_file: Path to pages.json
            output_dir: Output directory (defaults to same as input)
        """
        self.pages_file = Path(pages_file)
        self.output_dir = Path(output_dir) if output_dir else self.pages_file.parent
        
        # Derive input file paths
        base_name = self.pages_file.stem.replace("_pages", "")
        self.redirect_map_file = self.pages_file.parent / f"{base_name}_pages_redirect_map.json"
        self.canonical_clusters_file = self.pages_file.parent / f"{base_name}_pages_canonical_clusters.json"
        self.link_graph_file = self.pages_file.parent / f"{base_name}_pages_link_graph.json"
        
        # Data containers
        self.pages: List[Dict] = []
        self.redirect_map: Dict = {}
        self.canonical_clusters: Dict = {}
        self.link_graph: Dict = {}
        
        # Lookup dictionaries for fast access
        self.url_to_page: Dict[str, Dict] = {}
        self.url_to_cluster: Dict[str, Dict] = {}
        self.url_to_inlinks: Dict[str, int] = {}
        
        # Results
        self.indexability_pages: List[Dict] = []
        self.crawl_budget_report: Dict = {}
        self.indexability_issues: List[Dict] = []
    
    def load_data(self):
        """Load all required input files."""
        print("Loading input files...")
        
        # Load pages.json
        print(f"  Loading {self.pages_file.name}...")
        with open(self.pages_file, 'r', encoding='utf-8') as f:
            self.pages = json.load(f)
        print(f"    Loaded {len(self.pages)} pages")
        
        # Build URL lookup
        self.url_to_page = {page['url']: page for page in self.pages}
        
        # Load redirect_map.json
        if self.redirect_map_file.exists():
            print(f"  Loading {self.redirect_map_file.name}...")
            with open(self.redirect_map_file, 'r', encoding='utf-8') as f:
                self.redirect_map = json.load(f)
            print(f"    Loaded {len(self.redirect_map)} redirect entries")
        else:
            print(f"  Warning: {self.redirect_map_file.name} not found, skipping redirect resolution")
        
        # Load canonical_clusters.json
        if self.canonical_clusters_file.exists():
            print(f"  Loading {self.canonical_clusters_file.name}...")
            with open(self.canonical_clusters_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.canonical_clusters = data.get('clusters', [])
            print(f"    Loaded {len(self.canonical_clusters)} canonical clusters")
            
            # Build URL to cluster lookup
            for cluster in self.canonical_clusters:
                for member in cluster.get('members', []):
                    self.url_to_cluster[member['url']] = cluster
        else:
            print(f"  Warning: {self.canonical_clusters_file.name} not found, skipping canonical analysis")
        
        # Load link_graph.json
        if self.link_graph_file.exists():
            print(f"  Loading {self.link_graph_file.name}...")
            with open(self.link_graph_file, 'r', encoding='utf-8') as f:
                self.link_graph = json.load(f)
            print(f"    Loaded link graph data")
            
            # IMPROVEMENT 2: Build inlinks lookup AND resolve to final URLs
            for page_data in self.link_graph.get('pages', []):
                self.url_to_inlinks[page_data['url']] = page_data.get('inlinks', 0)
        else:
            print(f"  Warning: {self.link_graph_file.name} not found, skipping link analysis")
        
        # IMPROVEMENT 2: Resolve internal links to final URLs
        self._resolve_inlinks_to_final_urls()
        
        print("Data loading complete.\n")
    
    def _resolve_inlinks_to_final_urls(self):
        """IMPROVEMENT 2: Resolve internal links through redirects to get accurate link counts."""
        if not self.redirect_map:
            return
        
        resolved_inlinks = defaultdict(int)
        
        for url, inlink_count in self.url_to_inlinks.items():
            # Get final URL for this URL
            final_url = self.redirect_map.get(url, {}).get('final_url', url)
            
            # Add inlinks to final URL
            resolved_inlinks[final_url] += inlink_count
        
        # Update inlinks map with resolved counts
        self.url_to_inlinks = dict(resolved_inlinks)
    
    def resolve_final_url(self, url: str) -> Tuple[str, bool]:
        """
        Resolve URL to its final destination.
        
        Args:
            url: Original URL
            
        Returns:
            Tuple of (final_url, is_redirecting)
        """
        if url in self.redirect_map:
            final_url = self.redirect_map[url].get('final_url', url)
            is_redirecting = (url != final_url)
            return final_url, is_redirecting
        return url, False
    
    def check_canonical_authority(self, url: str, is_redirecting: bool = False) -> Dict:
        """
        Check canonical authority for a URL.
        
        IMPROVEMENT 1: Google ignores canonicals on redirecting URLs.
        
        Args:
            url: URL to check
            is_redirecting: Whether this URL redirects
            
        Returns:
            Dictionary with canonical info
        """
        # IMPROVEMENT 1: If URL redirects, canonical is ignored
        if is_redirecting:
            final_url = self.redirect_map.get(url, {}).get('final_url', url)
            return {
                "cluster_id": None,
                "is_cluster_leader": False,
                "canonical_target": final_url,
                "canonical_ignored": True,
                "canonical_ignored_reason": "redirect_precedence"
            }
        
        cluster = self.url_to_cluster.get(url)
        
        if not cluster:
            return {
                "cluster_id": None,
                "is_cluster_leader": True,  # Standalone page
                "canonical_target": None,
                "canonical_ignored": False
            }
        
        canonical_leader = cluster.get('canonical_leader')
        is_leader = (url == canonical_leader)
        
        # Get canonical chain depth if available
        chain_depth = cluster.get('chain_depth', 0)
        
        return {
            "cluster_id": cluster.get('cluster_id'),
            "is_cluster_leader": is_leader,
            "canonical_target": canonical_leader if not is_leader else None,
            "canonical_chain_depth": chain_depth,  # IMPROVEMENT 5
            "canonical_ignored": False
        }
    
    
    def check_crawlability(self, page: Dict) -> Tuple[bool, List[str]]:
        """
        IMPROVEMENT 4: Check if a page is crawlable (separate from indexability).
        
        Args:
            page: Page data dictionary
            
        Returns:
            Tuple of (is_crawlable, blocking_factors)
        """
        blocking_factors = []
        
        # Check robots.txt
        if page.get('blocked_by_robots', False):
            blocking_factors.append('blocked_by_robots')
        
        # Check status code
        status_code = page.get('status_code', 200)
        if status_code >= 400:
            blocking_factors.append(f'error_status_{status_code}')
        
        is_crawlable = len(blocking_factors) == 0
        return is_crawlable, blocking_factors
    
    def check_indexability(self, page: Dict, is_crawlable: bool) -> Tuple[bool, List[str]]:
        """
        Check if a page is indexable (requires crawlability first).
        
        IMPROVEMENT 4: Indexability = crawlable AND not noindex
        
        Args:
            page: Page data dictionary
            is_crawlable: Whether page is crawlable
            
        Returns:
            Tuple of (is_indexable, blocking_factors)
        """
        blocking_factors = []
        
        # Must be crawlable first
        if not is_crawlable:
            return False, ['not_crawlable']
        
        # Check meta noindex
        if page.get('noindex', False):
            blocking_factors.append('meta_noindex')
        
        is_indexable = len(blocking_factors) == 0
        return is_indexable, blocking_factors
    
    def check_seo_eligibility(self, page: Dict) -> Tuple[bool, List[str], bool]:
        """
        Check if a page is SEO eligible (worth indexing).
        
        IMPROVEMENT 2.2: Page-type aware thin content detection
        IMPROVEMENT 6: Single thin_content flag for reuse
        
        Args:
            page: Page data dictionary
            
        Returns:
            Tuple of (is_eligible, reasons, is_thin)
        """
        reasons = []
        
        # Get word count (use main content if available, otherwise raw)
        word_count = page.get('word_count_main', page.get('word_count_raw', 0))
        
        # IMPROVEMENT 2.2: Page-type aware thresholds
        page_type = page.get('page_type', 'content')
        
        # Define thresholds based on page type
        if page_type == 'tool':
            min_words = 50  # Tools can be interactive with less text
            thin_threshold = 100
        elif page_type in ['reference', 'documentation']:
            min_words = 150  # Reference pages need more depth
            thin_threshold = 200
        elif page_type == 'category':
            min_words = 75  # Category/hub pages can be lighter
            thin_threshold = 150
        else:
            # Default for blog, content, etc.
            min_words = CONFIG['min_word_count']
            thin_threshold = CONFIG['thin_content_threshold']
        
        # IMPROVEMENT 6: Single thin content flag
        is_thin = word_count < thin_threshold and not page.get('thin_content_exception', False)
        
        # Check word count against minimum
        if word_count < min_words:
            reasons.append(f'low_word_count_{word_count}')
        
        # Check page type
        if page_type in CONFIG['utility_page_types']:
            reasons.append(f'utility_page_type_{page_type}')
        
        # Flag thin content
        if is_thin:
            reasons.append('thin_content')
        
        # Check if URL has parameters (potential duplicate)
        if page.get('url_has_params', False):
            reasons.append('has_url_parameters')
        
        is_eligible = len(reasons) == 0
        return is_eligible, reasons, is_thin
    
    def parse_indexing_directive(self, page: Dict) -> Dict:
        """CRITICAL FIX 1: Parse indexing directive with index/follow separation
        
        Returns:
            {
                "index": bool,
                "follow": bool,
                "source": str (meta_robots | x_robots_tag | default)
            }
        """
        # Default: index, follow
        directive = {
            "index": True,
            "follow": True,
            "source": "default"
        }
        
        # Check meta_robots first
        meta_robots = page.get('meta_robots', '')
        if meta_robots:
            meta_lower = meta_robots.lower()
            directive["source"] = "meta_robots"
            
            # Parse directives
            if 'noindex' in meta_lower:
                directive["index"] = False
            elif 'none' in meta_lower:
                directive["index"] = False
                directive["follow"] = False
            
            if 'nofollow' in meta_lower:
                directive["follow"] = False
            elif 'none' in meta_lower:
                directive["follow"] = False
        
        # Check x_robots_tag (overrides meta_robots if present)
        x_robots = page.get('x_robots_tag', '')
        if x_robots:
            x_robots_lower = x_robots.lower()
            directive["source"] = "x_robots_tag"
            
            if 'noindex' in x_robots_lower:
                directive["index"] = False
            elif 'none' in x_robots_lower:
                directive["index"] = False
                directive["follow"] = False
            
            if 'nofollow' in x_robots_lower:
                directive["follow"] = False
            elif 'none' in x_robots_lower:
                directive["follow"] = False
        
        # Check noindex field (legacy support)
        if page.get('noindex', False):
            directive["index"] = False
            if directive["source"] == "default":
                directive["source"] = "noindex_field"
        
        return directive
    
    def get_primary_indexability_reason(self, page: Dict, is_indexable: bool, 
                                        is_redirecting: bool, canonical_info: Dict,
                                        indexing_directive: Dict) -> str:
        """CRITICAL FIX 2: Get primary indexability reason with priority ordering
        
        Priority order:
        1. redirect
        2. noindex
        3. canonicalized
        4. blocked_by_robots
        5. soft_404
        6. deep_url
        7. low_internal_links
        """
        if not is_indexable:
            # Priority 1: Redirect
            if is_redirecting:
                return "redirect"
            
            # Priority 2: Noindex
            if not indexing_directive["index"]:
                return "noindex"
            
            # Priority 3: Canonicalized
            if not canonical_info['is_cluster_leader']:
                return "canonicalized"
            
            # Priority 4: Blocked by robots
            if page.get('blocked_by_robots', False):
                return "blocked_by_robots"
            
            # Priority 5: Soft 404
            if page.get('status_code') == 404:
                return "soft_404"
        
        # Priority 6: Deep URL (if not indexable due to depth)
        url_depth = urlparse(page['url']).path.count('/')
        if url_depth > 5:
            return "deep_url"
        
        # Priority 7: Low internal links
        internal_links = self.url_to_inlinks.get(page['url'], 0)
        if internal_links < 3:
            return "low_internal_links"
        
        return "indexable"
    
    def get_indexability_decision(self, page: Dict, is_crawlable: bool, 
                                  is_redirecting: bool, canonical_info: Dict,
                                  indexing_directive: Dict, is_thin: bool) -> Dict:
        """GAP 1: Get indexability decision with Google's priority hierarchy
        
        Priority (Google's logic):
        1. Redirect
        2. Robots block
        3. noindex
        4. canonical
        5. status code
        
        Returns:
            {
                "status": "indexable" | "conditionally_indexable" | "non_indexable",
                "primary_reason": str,
                "secondary_reason": str | None
            }
        """
        decision = {
            "status": "indexable",
            "primary_reason": None,
            "secondary_reason": None
        }
        
        # Priority 1: Redirect (absolute blocker)
        if is_redirecting:
            decision["status"] = "non_indexable"
            decision["primary_reason"] = "redirect"
            return decision
        
        # Priority 2: Robots block (absolute blocker)
        if page.get('blocked_by_robots', False):
            decision["status"] = "non_indexable"
            decision["primary_reason"] = "blocked_by_robots"
            return decision
        
        # Priority 3: noindex (absolute blocker)
        if not indexing_directive["index"]:
            decision["status"] = "non_indexable"
            decision["primary_reason"] = "noindex"
            # Check for secondary reasons
            if not canonical_info['is_cluster_leader']:
                decision["secondary_reason"] = "canonical_mismatch"
            return decision
        
        # Priority 4: Canonical (conditional blocker)
        if not canonical_info['is_cluster_leader']:
            decision["status"] = "non_indexable"
            decision["primary_reason"] = "canonicalized"
            return decision
        
        # Priority 5: Status code (conditional blocker)
        status_code = page.get('status_code', 200)
        if status_code != 200:
            decision["status"] = "non_indexable"
            decision["primary_reason"] = f"status_{status_code}"
            return decision
        
        # GAP 2: Check for conditional indexability
        # Thin content → conditionally_indexable
        if is_thin:
            decision["status"] = "conditionally_indexable"
            decision["primary_reason"] = "thin_content"
            return decision
        
        # Parameter URLs → conditionally_indexable
        if page.get('url_has_params', False):
            decision["status"] = "conditionally_indexable"
            decision["primary_reason"] = "parameter_url"
            return decision
        
        # Deep URLs → conditionally_indexable
        url_depth = urlparse(page['url']).path.count('/')
        if url_depth > 5:
            decision["status"] = "conditionally_indexable"
            decision["primary_reason"] = "deep_url"
            return decision
        
        # Fully indexable
        decision["status"] = "indexable"
        decision["primary_reason"] = "indexable"
        return decision
    
    def is_refined_orphan(self, url: str, inlinks: int, canonical_info: Dict,
                         is_indexable: bool) -> bool:
        """FIX 3: Refined orphan detection
        
        An orphan page must be:
        - inlinks == 0
        - AND not cluster leader
        - AND indexable
        """
        if inlinks > 0:
            return False
        
        if canonical_info['is_cluster_leader']:
            return False  # Cluster leaders are intentional hubs
        
        if not is_indexable:
            return False  # Non-indexable pages can't be orphans
        
        return True
    
    def calculate_crawl_budget_grade(self, wasted_urls: int, total_urls: int) -> Tuple[str, float]:
        """FIX 4: Calculate normalized crawl budget grade
        
        Returns:
            (grade, waste_ratio)
        """
        waste_ratio = wasted_urls / total_urls if total_urls > 0 else 0.0
        
        if waste_ratio <= 0.10:
            grade = "GOOD"
        elif waste_ratio <= 0.25:
            grade = "MODERATE"
        else:
            grade = "POOR"
        
        return grade, waste_ratio
    
    def detect_soft_404(self, page: Dict) -> bool:
        """REFINEMENT 2: Heuristic soft-404 detection (POLISHED: homepage exception)
        
        Detects pages that return 200 but are actually 404s:
        - 200 status
        - Very low word count
        - "Page not found" patterns
        - Empty templates
        
        POLISH 1: Treat homepage/hub pages differently
        """
        status_code = page.get('status_code', 200)
        if status_code != 200:
            return False  # Not a soft-404 if already hard-404
        
        # POLISH 1: Disable soft-404 logic for homepage/hub pages
        page_type = page.get('page_type', 'content')
        is_homepage = page.get('is_homepage', False)
        if is_homepage or page_type in ['homepage', 'hub', 'docs_index', 'category']:
            return False  # Homepage/hub pages can have low word count
        
        word_count = page.get('word_count_main', page.get('word_count_raw', 0))
        title = (page.get('title') or '').lower()
        h1 = (page.get('h1') or '').lower()
        
        # Heuristic 1: Very low word count (< 50 words)
        if word_count < 50:
            return True
        
        # Heuristic 2: "Page not found" patterns
        not_found_patterns = ['not found', '404', 'page not found', 'does not exist', 'no longer available']
        if any(pattern in title or pattern in h1 for pattern in not_found_patterns):
            return True
        
        # Heuristic 3: Empty template (< 100 words + generic title)
        if word_count < 100:
            generic_titles = ['error', 'oops', 'sorry', 'unavailable']
            if any(generic in title for generic in generic_titles):
                return True
        
        return False
    
    def check_parameter_crawl_waste(self, url: str, page: Dict, canonical_info: Dict) -> Tuple[bool, str]:
        """REFINEMENT 3: Parameter crawl waste scoring with canonical/redirect checking
        
        Returns:
            (is_waste, reason)
        """
        if not page.get('url_has_params', False):
            return False, None
        
        # Check if parameter URL canonicalizes to clean URL
        if not canonical_info['is_cluster_leader']:
            canonical_leader = canonical_info.get('canonical_leader', '')
            # If canonical is clean (no params), this is duplicate crawl waste
            if canonical_leader and not urlparse(canonical_leader).query:
                return True, "parameter_url_canonicalized_to_clean"
        
        # Check if parameter URL redirects
        if self.redirect_map:
            redirect_record = self.redirect_map.get(url, {})
            final_url = redirect_record.get('final_url', url)
            if final_url != url and not urlparse(final_url).query:
                return True, "parameter_url_redirects_to_clean"
        
        # Parameter URL but no canonical/redirect resolution
        return False, None
    
    def calculate_issue_severity_weight(self, url: str, inlinks: int, 
                                        canonical_info: Dict) -> float:
        """REFINEMENT 4: Severity weighting by crawl frequency
        
        Weight issues by:
        - inlinks (crawl frequency)
        - depth (discoverability)
        - canonical leader status (importance)
        
        Returns:
            Weight multiplier (0.1 - 3.0)
        """
        weight = 1.0
        
        # Factor 1: Inlinks (crawl frequency)
        if inlinks >= 20:
            weight *= 2.0  # High-traffic page
        elif inlinks >= 10:
            weight *= 1.5
        elif inlinks >= 5:
            weight *= 1.2
        elif inlinks == 0:
            weight *= 0.5  # Orphan, lower priority
        
        # Factor 2: URL depth (discoverability)
        url_depth = urlparse(url).path.count('/')
        if url_depth <= 2:
            weight *= 1.3  # Shallow, more important
        elif url_depth >= 6:
            weight *= 0.7  # Deep, less important
        
        # Factor 3: Canonical leader status
        if canonical_info.get('is_cluster_leader', False):
            weight *= 1.5  # Leaders are more important
        
        # Cap weight between 0.1 and 3.0
        return round(min(max(weight, 0.1), 3.0), 2)
    
    def calculate_auto_severity(self, status: str, is_seo_eligible: bool,
                                crawl_budget_score: float, content_depth: str,
                                is_waste: bool) -> str:
        """POLISH 3: Auto-derive severity from multiple signals
        
        Calculate severity from:
        - indexability_status
        - seo_eligible
        - crawl_budget_score
        - content_depth
        
        Returns:
            Severity level: CRITICAL | HIGH | MEDIUM | LOW
        """
        # CRITICAL: Non-indexable with high crawl waste
        if status == "NON_INDEXABLE" and crawl_budget_score > 0.7:
            return "CRITICAL"
        
        # CRITICAL: Crawl waste on high-quality content
        if is_waste and content_depth == "HIGH":
            return "CRITICAL"
        
        # HIGH: Indexable but not SEO eligible with good content
        if status == "INDEXABLE_BUT_NOT_ELIGIBLE" and content_depth in ["HIGH", "MEDIUM"]:
            return "HIGH"
        
        # HIGH: Non-indexable with medium crawl waste
        if status == "NON_INDEXABLE" and crawl_budget_score > 0.4:
            return "HIGH"
        
        # MEDIUM: Crawl waste on medium content
        if is_waste and content_depth == "MEDIUM":
            return "MEDIUM"
        
        # MEDIUM: Indexable but not eligible with low content
        if status == "INDEXABLE_BUT_NOT_ELIGIBLE":
            return "MEDIUM"
        
        # LOW: Everything else
        return "LOW"
    
    def detect_crawl_waste(self, url: str, page: Dict, final_url: str, 
                          is_redirecting: bool, canonical_info: Dict,
                          is_indexable: bool, is_thin: bool) -> Tuple[bool, Optional[str], float]:
        """
        Detect if URL is wasting crawl budget.
        
        IMPROVEMENT 3: Parameter URLs only flagged if canonicalized/redirected
        IMPROVEMENT 6: Use is_thin flag consistently
        NEW: Redirect waste classification
        NEW: Numeric crawl budget score (0.0 = perfect, 1.0 = total waste)
        
        Args:
            url: Original URL
            page: Page data
            final_url: Final URL after redirects
            is_redirecting: Whether URL redirects
            canonical_info: Canonical cluster info
            is_indexable: Whether page is indexable
            is_thin: Whether page has thin content
            
        Returns:
            Tuple of (is_waste, waste_reason, crawl_budget_score)
        """
        internal_links = self.url_to_inlinks.get(final_url, 0)  # IMPROVEMENT 2: Use final_url
        
        # Initialize crawl budget score (0.0 = perfect, 1.0 = total waste)
        crawl_budget_score = 0.0
        
        # IMPROVEMENT 2: Redirecting pages are ALWAYS crawl waste
        if is_redirecting:
            crawl_budget_score += 0.5  # Base penalty for redirect
            if internal_links > 0:
                crawl_budget_score += 0.3  # Additional penalty for internal links
                return True, f"REDIRECTING_URL_with_{internal_links}_internal_links", min(crawl_budget_score, 1.0)
            return True, "REDIRECTING_URL", min(crawl_budget_score, 1.0)
        
        # Canonicalized URLs with internal links = waste
        if not canonical_info['is_cluster_leader'] and internal_links > 0:
            crawl_budget_score += 0.4  # Canonical penalty
            crawl_budget_score += min(internal_links / 10, 0.3)  # Link count penalty
            return True, f"canonicalized_with_{internal_links}_internal_links", min(crawl_budget_score, 1.0)
        
        # Non-indexable with internal links = waste
        if not is_indexable and internal_links > 0:
            crawl_budget_score += 0.6  # High penalty for non-indexable
            crawl_budget_score += min(internal_links / 10, 0.2)  # Link count penalty
            return True, f"non_indexable_with_{internal_links}_internal_links", min(crawl_budget_score, 1.0)
        
        # IMPROVEMENT 6: Use is_thin flag consistently
        # Thin content with internal links = waste
        if is_thin and internal_links > 0:
            crawl_budget_score += 0.3  # Moderate penalty for thin
            crawl_budget_score += min(internal_links / 10, 0.2)  # Link count penalty
            return True, f"thin_content_with_{internal_links}_internal_links", min(crawl_budget_score, 1.0)
        
        # IMPROVEMENT 3: Parameter URLs only waste if canonicalized/redirected/not leader
        if page.get('url_has_params', False):
            if not canonical_info['is_cluster_leader']:
                crawl_budget_score += 0.2  # Minor penalty for parameter duplicate
                return True, "parameter_url_duplicate", min(crawl_budget_score, 1.0)
        
        # Calculate score for non-waste pages (small penalties for minor issues)
        if not canonical_info['is_cluster_leader']:
            crawl_budget_score += 0.1  # Canonicalized but no links
        if is_thin:
            crawl_budget_score += 0.05  # Thin but no links
        
        return False, None, crawl_budget_score
    
    def classify_indexability(self, page: Dict, is_indexable: bool, 
                             is_seo_eligible: bool) -> str:
        """
        Classify final indexability status.
        
        Args:
            page: Page data
            is_indexable: Whether page is indexable
            is_seo_eligible: Whether page is SEO eligible
            
        Returns:
            Indexability status string
        """
        crawlable = page.get('status_code', 200) == 200
        
        if not crawlable or not is_indexable:
            return "NON_INDEXABLE"
        elif is_indexable and is_seo_eligible:
            return "INDEXABLE_AND_VALID"
        else:
            return "INDEXABLE_BUT_NOT_ELIGIBLE"
    
    def generate_recommendation(self, status: str, is_waste: bool, 
                               waste_reason: Optional[str],
                               canonical_info: Dict) -> str:
        """
        Generate actionable recommendation.
        
        Args:
            status: Indexability status
            is_waste: Whether URL wastes crawl budget
            waste_reason: Reason for waste
            canonical_info: Canonical info
            
        Returns:
            Recommendation string
        """
        if status == "INDEXABLE_AND_VALID" and not is_waste:
            return "Keep indexed"
        
        if is_waste:
            if "redirect" in waste_reason:
                return "Update internal links to point to final URL"
            elif "canonicalized" in waste_reason:
                return f"Update internal links to point to canonical URL: {canonical_info['canonical_target']}"
            elif "non_indexable" in waste_reason:
                return "Remove internal links or make page indexable"
            elif "thin_content" in waste_reason:
                return "Improve content quality or consolidate with other pages"
            elif "parameter" in waste_reason:
                return "Use canonical tags or configure URL parameters in GSC"
        
        if status == "NON_INDEXABLE":
            return "Fix indexability issues or exclude from crawl"
        
        if status == "INDEXABLE_BUT_NOT_ELIGIBLE":
            return "Improve content quality or use noindex"
        
        return "Review manually"
    
    def build_indexability_reasons(self, page: Dict, is_indexable: bool, 
                                   is_crawlable: bool, is_redirecting: bool,
                                   canonical_info: Dict, internal_links: int) -> List[str]:
        """
        Build comprehensive indexability reason codes.
        
        NEW IMPROVEMENT 1: Explain WHY a page is indexable or not.
        """
        reasons = []
        
        if is_indexable:
            # Positive reasons
            if canonical_info['is_cluster_leader']:
                reasons.append("self_canonical")
            if not is_redirecting:
                reasons.append("passes_redirect_resolution")
            if not page.get('blocked_by_robots', False):
                reasons.append("allowed_by_robots")
            if not page.get('noindex', False):
                reasons.append("no_noindex_meta")
            if internal_links > 0:
                reasons.append("linked_internally")
            if page.get('status_code', 200) == 200:
                reasons.append("returns_200")
        else:
            # Negative reasons
            if not canonical_info['is_cluster_leader']:
                reasons.append("canonicalized_to_other")
            if page.get('noindex', False):
                reasons.append("noindex_meta")
            if is_redirecting:
                reasons.append("redirect_target")
            if page.get('blocked_by_robots', False):
                reasons.append("blocked_by_robots")
            status_code = page.get('status_code', 200)
            if status_code >= 400:
                reasons.append(f"error_status_{status_code}")
        
        return reasons
    
    def build_seo_exclusion_reasons(self, is_seo_eligible: bool, is_thin: bool,
                                    eligibility_reasons: List[str],
                                    internal_links: int) -> List[str]:
        """
        Build SEO exclusion reasons.
        
        NEW IMPROVEMENT 2: Explain why page is not SEO-eligible.
        """
        if is_seo_eligible:
            return []
        
        exclusion_reasons = []
        
        if is_thin:
            exclusion_reasons.append("thin_content")
        if internal_links == 0:
            exclusion_reasons.append("low_internal_links")
        
        for reason in eligibility_reasons:
            if reason not in exclusion_reasons and "thin" not in reason:
                exclusion_reasons.append(reason)
        
        return exclusion_reasons
    
    def calculate_priority_score(self, status: str, is_waste: bool,
                                 internal_links: int, canonical_info: Dict,
                                 word_count: int, is_thin: bool,
                                 crawl_budget_score: float) -> float:
        """
        Calculate numeric priority score (0.0 = low priority, 1.0 = critical).
        
        NEW IMPROVEMENT 4: Numeric priority based on multiple signals.
        """
        priority_score = 0.0
        
        # Base score from crawl budget waste
        priority_score += crawl_budget_score * 0.4
        
        # Internal links signal
        if is_waste and internal_links > 0:
            priority_score += min(internal_links / 20, 0.3)
        
        # Canonical signal
        if not canonical_info['is_cluster_leader']:
            priority_score += 0.1
        
        # Content depth signal
        if is_thin:
            priority_score += 0.1
        elif word_count > 500:
            priority_score -= 0.05
        
        # Status-based adjustments
        if status == "NON_INDEXABLE":
            priority_score += 0.2
        elif status == "INDEXABLE_AND_VALID":
            priority_score -= 0.1
        
        # Orphan penalty
        if status == "INDEXABLE_AND_VALID" and internal_links == 0:
            priority_score += 0.15
        
        return min(max(priority_score, 0.0), 1.0)
    
    def analyze(self):
        """Run the complete indexability analysis."""
        print("Analyzing indexability and crawl budget...\n")
        
        for page in self.pages:
            url = page['url']
            
            # Step 1: Resolve final URL
            final_url, is_redirecting = self.resolve_final_url(url)
            
            # Step 2: Check canonical authority (IMPROVEMENT 1: pass is_redirecting)
            canonical_info = self.check_canonical_authority(url, is_redirecting)
            
            # Step 3: Check crawlability (IMPROVEMENT 4: separate from indexability)
            is_crawlable, crawlability_factors = self.check_crawlability(page)
            
            # Step 4: Check indexability (IMPROVEMENT 4: requires crawlability)
            is_indexable, indexability_factors = self.check_indexability(page, is_crawlable)
            
            # Step 5: Check SEO eligibility (IMPROVEMENT 2.2 + 6: returns is_thin)
            is_seo_eligible, eligibility_reasons, is_thin = self.check_seo_eligibility(page)
            
            # REFINEMENT 1: Parse indexing directive (index/follow separation)
            indexing_directive = self.parse_indexing_directive(page)
            
            # REFINEMENT 2: Detect soft-404
            is_soft_404 = self.detect_soft_404(page)
            
            # REFINEMENT 3: Check parameter crawl waste
            is_param_waste, param_waste_reason = self.check_parameter_crawl_waste(
                url, page, canonical_info
            )
            
            # Step 6: Detect crawl waste (NEW: returns crawl_budget_score)
            is_waste, waste_reason, crawl_budget_score = self.detect_crawl_waste(
                url, page, final_url, is_redirecting, 
                canonical_info, is_indexable, is_thin
            )
            
            # Override waste if parameter waste detected
            if is_param_waste:
                is_waste = True
                waste_reason = param_waste_reason
            
            # Step 7: Classify indexability
            status = self.classify_indexability(page, is_indexable, is_seo_eligible)
            
            # Generate recommendation
            recommendation = self.generate_recommendation(
                status, is_waste, waste_reason, canonical_info
            )
            
            # Build indexability signals
            indexing_signals = {
                "noindex": page.get('noindex', False),
                "canonicalized": not canonical_info['is_cluster_leader'],
                "redirected": is_redirecting,
                "blocked_by_robots": page.get('blocked_by_robots', False)
            }
            
            # IMPROVEMENT 2.1: Add quality signals for granularity
            word_count = page.get('word_count_main', page.get('word_count_raw', 0))
            page_type = page.get('page_type', 'content')
            
            # NEW IMPROVEMENT 4: Content type vs indexability conflict detection
            content_type_conflict = False
            if page_type in ['docs_index', 'api_reference', 'category']:
                # These types are OK with thin content
                if is_thin:
                    content_type_conflict = False  # Expected
            elif page_type == 'content' and is_thin:
                content_type_conflict = True  # Content pages should not be thin
            
            quality_signals = {
                "is_thin": is_thin,
                "word_count": word_count,
                "page_type": page_type,
                "content_depth": "HIGH" if word_count > 500 else "MEDIUM" if word_count > 200 else "LOW",
                "content_type_conflict": content_type_conflict  # NEW
            }
            
            # IMPROVEMENT 2.1: Add indexability reason for clarity
            indexability_reason = None
            if not is_indexable:
                if crawlability_factors:
                    indexability_reason = crawlability_factors[0]
                elif indexability_factors:
                    indexability_reason = indexability_factors[0]
            elif not is_seo_eligible:
                if is_thin:
                    indexability_reason = "THIN_CONTENT"
                elif eligibility_reasons:
                    indexability_reason = eligibility_reasons[0].upper()
            
            # Get internal links count
            internal_links = self.url_to_inlinks.get(final_url, 0)
            
            # NEW IMPROVEMENT 1: Build indexability reason codes
            indexability_reasons = self.build_indexability_reasons(
                page, is_indexable, is_crawlable, is_redirecting,
                canonical_info, internal_links
            )
            
            # NEW IMPROVEMENT 2: Build SEO exclusion reasons
            seo_exclusion_reasons = self.build_seo_exclusion_reasons(
                is_seo_eligible, is_thin, eligibility_reasons, internal_links
            )
            
            # NEW IMPROVEMENT 4: Calculate numeric priority score
            priority_score = self.calculate_priority_score(
                status, is_waste, internal_links, canonical_info,
                word_count, is_thin, crawl_budget_score
            )
            
            # IMPROVEMENT 2.3: Enhanced crawl budget impact
            cluster_size = 1
            if canonical_info.get('cluster_id'):
                # Try to get cluster size from canonical clusters
                cluster = self.url_to_cluster.get(url)
                if cluster:
                    cluster_size = len(cluster.get('members', []))
            
            crawl_budget_impact = {
                "is_waste": is_waste,
                "waste_reason": waste_reason,
                "internal_links_pointing": internal_links,  # IMPROVEMENT 1: Internal links signal
                "cluster_size": cluster_size,  # IMPROVEMENT 2.3
                "crawl_budget_score": round(crawl_budget_score, 3)  # NEW: Numeric score
            }
            
            # NEW IMPROVEMENT 1: Internal Links Signal for Priority
            # NEW IMPROVEMENT 3: Robots.txt Granularity
            # IMPROVEMENT 2.5: Enhanced priority scoring
            priority = "LOW"
            blocked_by_robots = page.get('blocked_by_robots', False)
            
            # Critical priority cases
            if blocked_by_robots and internal_links > 0:
                priority = "CRITICAL"  # NEW: Robots blocked but internally linked
            elif is_waste and waste_reason:
                if "REDIRECTING_URL" in waste_reason:
                    priority = "CRITICAL" if internal_links > 5 else "HIGH"  # NEW: Redirect severity
                elif "non_indexable" in waste_reason:
                    priority = "HIGH"
                elif "canonicalized" in waste_reason:
                    priority = "HIGH"
                elif "thin_content" in waste_reason:
                    priority = "MEDIUM"
            # NEW: Indexable pages with internal links signal
            elif status == "INDEXABLE_AND_VALID":
                if internal_links == 0:
                    priority = "LOW"  # Orphan indexable page - missed opportunity
                elif internal_links > 10:
                    priority = "LOW"  # Strong internal links - good
                else:
                    priority = "LOW"
            elif status == "INDEXABLE_BUT_NOT_ELIGIBLE":
                if content_type_conflict:
                    priority = "HIGH"  # NEW: Content page that's thin
                else:
                    priority = "MEDIUM"
            elif blocked_by_robots and internal_links == 0:
                priority = "LOW"  # NEW: Blocked and orphan - not a problem
            
            # Combine all blocking factors
            all_blocking_factors = crawlability_factors + indexability_factors + eligibility_reasons
            
            # REFINEMENT 4: Calculate severity weight
            severity_weight = self.calculate_issue_severity_weight(
                url, internal_links, canonical_info
            )
            
            # REFINEMENT 1: Detect nofollow pages (link graph disruption)
            nofollow_detected = indexing_directive["index"] and not indexing_directive["follow"]
            
            # POLISH 3: Calculate auto-derived severity
            content_depth = "HIGH" if word_count > 500 else "MEDIUM" if word_count > 200 else "LOW"
            auto_severity = self.calculate_auto_severity(
                status, is_seo_eligible, crawl_budget_score, content_depth, is_waste
            )
            
            # Create indexability page entry with NEW STRATEGIC FIELDS
            indexability_page = {
                "url": url,
                "final_url": final_url,
                "indexability_status": status,
                "indexability_reason": indexability_reason,  # Legacy single reason
                "indexability_reasons": indexability_reasons,  # NEW IMPROVEMENT 1: Comprehensive reasons
                "indexable": is_indexable,
                "crawlable": is_crawlable,
                "is_crawlable": is_crawlable,  # GAP 4: Explicit crawlability
                "seo_eligible": is_seo_eligible,  # NEW IMPROVEMENT 2: Explicit flag
                "seo_exclusion_reasons": seo_exclusion_reasons,  # NEW IMPROVEMENT 2: Why not SEO-eligible
                "blocking_factors": all_blocking_factors,
                "indexing_signals": indexing_signals,
                "indexing_directive": indexing_directive,  # REFINEMENT 1: index/follow separation
                "is_soft_404": is_soft_404,  # REFINEMENT 2: Soft-404 detection
                "nofollow_detected": nofollow_detected,  # REFINEMENT 1: Link graph disruption
                "canonical_info": canonical_info,
                "crawl_budget_impact": crawl_budget_impact,
                "quality_signals": quality_signals,
                "priority": priority,  # Text priority (CRITICAL/HIGH/MEDIUM/LOW)
                "indexability_priority": round(priority_score, 3),  # NEW IMPROVEMENT 4: Numeric priority
                "severity_weight": severity_weight,  # REFINEMENT 4: Crawl frequency weighting
                "auto_severity": auto_severity,  # POLISH 3: Auto-derived severity
                "recommendation": recommendation
            }
            
            self.indexability_pages.append(indexability_page)
        
        print(f"Analyzed {len(self.indexability_pages)} pages\n")
    
    def generate_crawl_budget_report(self):
        """Generate the crawl budget summary report."""
        print("Generating crawl budget report...")
        
        total_urls = len(self.indexability_pages)
        indexable_valid = sum(1 for p in self.indexability_pages 
                             if p['indexability_status'] == 'INDEXABLE_AND_VALID')
        wasted_crawl = sum(1 for p in self.indexability_pages 
                          if p['crawl_budget_impact']['is_waste'])
        
        # Calculate efficiency score
        crawl_efficiency = indexable_valid / total_urls if total_urls > 0 else 0
        
        # GAP 3: Breakdown waste by category (ALWAYS populate all categories)
        waste_breakdown = {
            "redirects": 0,
            "canonicalized": 0,
            "noindex": 0,
            "blocked_by_robots": 0,
            "duplicate_parameters": 0,
            "thin_content": 0,
            "non_indexable_with_links": 0
        }
        
        for page in self.indexability_pages:
            if page['crawl_budget_impact']['is_waste']:
                reason = page['crawl_budget_impact']['waste_reason']
                if 'redirect' in reason:
                    waste_breakdown['redirects'] += 1
                elif 'canonicalized' in reason:
                    waste_breakdown['canonicalized'] += 1
                elif 'noindex' in reason:
                    waste_breakdown['noindex'] += 1
                elif 'robots' in reason:
                    waste_breakdown['blocked_by_robots'] += 1
                elif 'parameter' in reason:
                    waste_breakdown['duplicate_parameters'] += 1
                elif 'thin_content' in reason:
                    waste_breakdown['thin_content'] += 1
                elif 'non_indexable' in reason:
                    waste_breakdown['non_indexable_with_links'] += 1
        
        # FIX 4: Calculate crawl budget grade
        crawl_budget_grade, waste_ratio = self.calculate_crawl_budget_grade(wasted_crawl, total_urls)
        
        # Top waste sources
        top_waste_sources = []
        waste_fixes = {
            'redirects': 'Update internal links to point to final URLs',
            'canonicalized': 'Internal links should point to canonical leader URLs',
            'noindex': 'Remove internal links or add to robots.txt',
            'blocked_by_robots': 'Update robots.txt or remove internal links',
            'duplicate_parameters': 'Use canonical tags or configure URL parameters in GSC',
            'thin_content': 'Improve content quality or consolidate pages',
            'non_indexable_with_links': 'Remove internal links or fix indexability issues'
        }
        
        for waste_type, count in sorted(waste_breakdown.items(), 
                                       key=lambda x: x[1], reverse=True):
            if count > 0:
                top_waste_sources.append({
                    "type": waste_type.upper(),
                    "count": count,
                    "fix": waste_fixes.get(waste_type, 'Review manually')
                })
        
        self.crawl_budget_report = {
            "total_urls": total_urls,
            "indexable_urls": indexable_valid,
            "wasted_crawl_urls": wasted_crawl,
            "crawl_efficiency_score": round(crawl_efficiency, 3),
            "crawl_budget_grade": crawl_budget_grade,  # NEW: FIX 4
            "waste_ratio": round(waste_ratio, 3),  # NEW: FIX 4
            "waste_breakdown": waste_breakdown,  # UPDATED: GAP 3
            "top_waste_sources": top_waste_sources
        }
        
        print(f"  Total URLs: {total_urls}")
        print(f"  Indexable & Valid: {indexable_valid}")
        print(f"  Wasted Crawl: {wasted_crawl}")
        print(f"  Efficiency Score: {crawl_efficiency:.1%}\n")
    
    def generate_indexability_issues(self):
        """Generate actionable issues for the audit engine."""
        print("Generating indexability issues...")
        
        issues = []
        issue_id_counter = 1
        
        # Group pages by waste type
        waste_groups = defaultdict(list)
        for page in self.indexability_pages:
            if page['crawl_budget_impact']['is_waste']:
                reason = page['crawl_budget_impact']['waste_reason']
                waste_groups[reason].append(page['url'])
        
        # Generate issues for each waste type
        for waste_reason, urls in waste_groups.items():
            count = len(urls)
            
            # Determine severity and issue type
            if 'REDIRECTING_URL' in waste_reason or 'redirect' in waste_reason:
                severity = 'critical'
                issue_type = 'redirect_waste'
                title = 'Redirecting URLs Wasting Crawl Budget'
                description = f'{count} URLs redirect but still receive internal links'
                impact = 'indexation_loss'  # NEW IMPROVEMENT 5: Impact type
                fix = 'Update internal links to point directly to final destination URLs'
            elif 'canonicalized' in waste_reason:
                severity = 'high'
                issue_type = 'canonical_conflict'  # NEW IMPROVEMENT 5
                title = 'Canonicalized URLs Wasting Crawl Budget'
                description = f'{count} URLs are canonicalized but still receive internal links'
                impact = 'indexation_loss'
                fix = 'Update internal links to point to canonical leader URLs'
            elif 'non_indexable' in waste_reason:
                severity = 'high'
                issue_type = 'indexability_blocking'  # NEW IMPROVEMENT 5
                title = 'Non-Indexable URLs Receiving Internal Links'
                description = f'{count} non-indexable URLs still receive internal links'
                impact = 'crawl_budget_waste'
                fix = 'Remove internal links or fix indexability issues (robots.txt, noindex)'
            elif 'thin_content' in waste_reason:
                severity = 'medium'
                issue_type = 'content_quality'  # NEW IMPROVEMENT 5
                title = 'Thin Content Pages Wasting Crawl Budget'
                description = f'{count} thin content pages receive internal links'
                impact = 'crawl_budget_waste'
                fix = 'Improve content quality, consolidate pages, or remove internal links'
            elif 'parameter' in waste_reason:
                severity = 'medium'
                issue_type = 'duplicate_content'  # NEW IMPROVEMENT 5
                title = 'Parameter URLs Potentially Wasting Crawl Budget'
                description = f'{count} URLs with parameters may create duplicate content'
                impact = 'crawl_budget_waste'
                fix = 'Use canonical tags or configure URL parameters in Google Search Console'
            else:
                continue
            
            # Calculate priority score
            priority_score = count * (4 if severity == 'critical' else 
                                    3 if severity == 'high' else 
                                    2 if severity == 'medium' else 1)
            
            # NEW IMPROVEMENT 5: Enhanced issue structure
            issue = {
                "rule_id": f"IDX_{issue_id_counter:03d}",
                "issue_type": issue_type,  # NEW
                "severity": severity,
                "title": title,
                "description": description,
                "impact": impact,  # NEW: Structured impact type
                "affected_urls": urls[:100],  # Limit to first 100
                "affected_count": count,
                "how_to_fix": fix,
                "recommended_action": fix,  # NEW: Alias for consistency
                "priority_score": priority_score
            }
            
            issues.append(issue)
            issue_id_counter += 1
        
        # Sort by priority score
        self.indexability_issues = sorted(issues, 
                                         key=lambda x: x['priority_score'], 
                                         reverse=True)
        
        print(f"  Generated {len(self.indexability_issues)} issues\n")
    
    def write_outputs(self):
        """Write all output files."""
        print("Writing output files...")
        
        # Ensure output directory exists
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Derive base name
        base_name = self.pages_file.stem.replace("_pages", "")
        
        # Write indexability_pages.json
        output_file = self.output_dir / f"{base_name}_indexability_pages.json"
        print(f"  Writing {output_file.name}...")
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(self.indexability_pages, f, indent=2, ensure_ascii=False)
        print(f"    Wrote {len(self.indexability_pages)} pages")
        
        # Write crawl_budget_report.json
        output_file = self.output_dir / f"{base_name}_crawl_budget_report.json"
        print(f"  Writing {output_file.name}...")
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(self.crawl_budget_report, f, indent=2, ensure_ascii=False)
        
        # Write indexability_issues.json
        output_file = self.output_dir / f"{base_name}_indexability_issues.json"
        print(f"  Writing {output_file.name}...")
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(self.indexability_issues, f, indent=2, ensure_ascii=False)
        print(f"    Wrote {len(self.indexability_issues)} issues")
        
        print("\nOutput files written successfully!")
    
    def run(self):
        """Run the complete analysis pipeline."""
        self.load_data()
        self.analyze()
        self.generate_crawl_budget_report()
        self.generate_indexability_issues()
        self.write_outputs()


def main():
    """Main entry point."""
    import sys
    
    # Check if paths provided via command line
    if len(sys.argv) >= 2:
        pages_file = sys.argv[1]
        output_dir = sys.argv[2] if len(sys.argv) > 2 else None
    else:
        # Interactive mode - prompt user for input
        print("=" * 70)
        print("🔍 INDEXABILITY & CRAWL BUDGET ANALYZER")
        print("=" * 70)
        print("\nEnter path to your pages JSON file:")
        print("Example: crawler_output/developer_mozilla_org_20251220_054821_pages.json")
        print()
        
        pages_file = input("Pages JSON path: ").strip()
        
        if not pages_file:
            print("❌ Error: Pages file path is required")
            sys.exit(1)
        
        if not Path(pages_file).exists():
            print(f"❌ Error: File not found: {pages_file}")
            sys.exit(1)
        
        print("\nEnter output directory (press Enter to use same directory as input):")
        output_dir = input("Output directory (optional): ").strip() or None
        
        if output_dir:
            print(f"✓ Output will be saved to: {output_dir}")
        else:
            print(f"✓ Output will be saved to: {Path(pages_file).parent}")
    
    print()
    print("=" * 70)
    print("🔍 INDEXABILITY & CRAWL BUDGET ANALYZER")
    print("=" * 70)
    print()
    
    analyzer = IndexabilityAnalyzer(pages_file, output_dir)
    analyzer.run()
    
    print("\n" + "="*70)
    print("✅ INDEXABILITY ANALYSIS COMPLETE")
    print("="*70)
    print(f"\n📊 Results:")
    print(f"  Crawl Efficiency Score: {analyzer.crawl_budget_report['crawl_efficiency_score']:.1%}")
    print(f"  Indexable URLs: {analyzer.crawl_budget_report['indexable_urls']}")
    print(f"  Wasted Crawl URLs: {analyzer.crawl_budget_report['wasted_crawl_urls']}")
    print(f"  Issues Found: {len(analyzer.indexability_issues)}")
    print("="*70)


if __name__ == "__main__":
    main()
