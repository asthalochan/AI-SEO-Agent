"""
Content Quality Analyzer

Answers the core question: "Which indexable pages actually deserve rankings?"

This module evaluates:
- Content depth (word count, heading structure)
- Internal authority alignment
- Canonical cluster role
- Overall quality scoring and ranking potential

Required Input:
- pages.json (from crawler) - REQUIRED

Optional Inputs (enhance analysis if available):
- indexability_pages.json (from indexability analyzer) - Adds indexability context
- link_graph.json (internal authority) - Adds internal authority scoring
- canonical_clusters.json (cluster leadership) - Adds cluster role evaluation

Note: Module works with just pages.json and gracefully enhances when other files are present.

Outputs:
- content_quality_pages.json (per-URL quality analysis)
- content_quality_issues.json (actionable issues)
- content_quality_summary.json (executive summary)
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from collections import defaultdict
from urllib.parse import urlparse


# Configuration
CONFIG = {
    # Context-aware word count thresholds
    "word_count_thresholds": {
        "content": 600,
        "docs": 300,
        "legal": 200,
        "api_reference": 150,
        "glossary": 100
    },
    
    # Reading speed (words per minute)
    "reading_speed_wpm": 225,
    
    # Heading structure expectations
    "expected_h2_per_1000_words": 5,
    "expected_h3_per_1000_words": 8,
    
    # Internal authority thresholds
    "high_authority_inlinks": 20,
    "medium_authority_inlinks": 10,
    
    # Quality grade thresholds (BLOCKER 2: Lowered A threshold)
    "grade_thresholds": {
        "A": 0.80,  # FIXED: Was 0.85, now reachable
        "B": 0.70,
        "C": 0.50,
        "D": 0.0
    },
    
    # Intent-aware heading thresholds for over-optimization detection
    "heading_thresholds": {
        "article": {"h2_max": 15, "h3_max": 30},
        "reference": {"h2_max": 40, "h3_max": 80},
        "index": {"h2_max": 60, "h3_max": 120},
        "hub": {"h2_max": 60, "h3_max": 120},
        "utility": {"h2_max": 10, "h3_max": 20}
    }
}


class ContentQualityAnalyzer:
    """Main analyzer class for content quality assessment."""
    
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
        self.indexability_file = self.pages_file.parent / f"{base_name}_indexability_pages.json"
        self.link_graph_file = self.pages_file.parent / f"{base_name}_pages_link_graph.json"
        self.canonical_clusters_file = self.pages_file.parent / f"{base_name}_pages_canonical_clusters.json"
        self.redirect_map_file = self.pages_file.parent / f"{base_name}_pages_redirect_map.json"  # NEW: FIX 1
        
        # Data containers
        self.pages: List[Dict] = []
        self.indexability_pages: List[Dict] = []
        self.link_graph: Dict = {}
        self.canonical_clusters: List[Dict] = []
        self.redirect_map: Dict = {}  # NEW: FIX 1
        
        # Lookup dictionaries
        self.url_to_page: Dict[str, Dict] = {}
        self.url_to_indexability: Dict[str, Dict] = {}
        self.url_to_inlinks: Dict[str, int] = {}  # Will use content_inlinks
        self.url_to_cluster: Dict[str, Dict] = {}
        
        # Results
        self.quality_pages: List[Dict] = []
        self.quality_issues: List[Dict] = []
        self.quality_summary: Dict = {}
    
    def load_data(self):
        """
        Load input files.
        
        Required:
        - pages.json
        
        Optional (gracefully handled if missing):
        - indexability_pages.json
        - link_graph.json
        - canonical_clusters.json
        """
        print("Loading input files...")
        print()
        
        # Load pages.json (REQUIRED)
        print(f"  ✓ Loading {self.pages_file.name} (REQUIRED)...")
        with open(self.pages_file, 'r', encoding='utf-8') as f:
            self.pages = json.load(f)
        print(f"    Loaded {len(self.pages)} pages")
        self.url_to_page = {page['url']: page for page in self.pages}
        
        # Load indexability_pages.json (OPTIONAL)
        if self.indexability_file.exists():
            print(f"  ✓ Loading {self.indexability_file.name} (OPTIONAL)...")
            with open(self.indexability_file, 'r', encoding='utf-8') as f:
                self.indexability_pages = json.load(f)
            print(f"    Loaded {len(self.indexability_pages)} indexability records")
            self.url_to_indexability = {page['url']: page for page in self.indexability_pages}
        else:
            print(f"  ⚠ {self.indexability_file.name} not found (OPTIONAL)")
            print(f"    → is_indexable and seo_eligible will default to False")
        
        # Load link_graph.json (OPTIONAL)
        if self.link_graph_file.exists():
            print(f"  ✓ Loading {self.link_graph_file.name} (OPTIONAL)...")
            with open(self.link_graph_file, 'r', encoding='utf-8') as f:
                self.link_graph = json.load(f)
            print(f"    Loaded link graph data")
            
            # Build inlinks lookup - FIX 1: Use content_inlinks for better accuracy
            for page_data in self.link_graph.get('pages', []):
                # Prefer content_inlinks over inlinks (more accurate for limited crawls)
                content_inlinks = page_data.get('content_inlinks', 0)
                inlinks = page_data.get('inlinks', 0)
                # Use whichever is higher (content_inlinks is usually more accurate)
                self.url_to_inlinks[page_data['url']] = max(content_inlinks, inlinks)
        else:
            print(f"  ⚠ {self.link_graph_file.name} not found (OPTIONAL)")
            print(f"    → Internal authority scores will be 0.0")
        
        # Load canonical_clusters.json (OPTIONAL)
        if self.canonical_clusters_file.exists():
            print(f"  ✓ Loading {self.canonical_clusters_file.name} (OPTIONAL)...")
            with open(self.canonical_clusters_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.canonical_clusters = data.get('clusters', [])
            print(f"    Loaded {len(self.canonical_clusters)} canonical clusters")
            
            # Build URL to cluster lookup
            for cluster in self.canonical_clusters:
                for member in cluster.get('members', []):
                    self.url_to_cluster[member['url']] = cluster
        else:
            print(f"  ⚠ {self.canonical_clusters_file.name} not found (OPTIONAL)")
            print(f"    → Cluster role scores will be neutral (0.5)")
        
        # Load redirect_map.json (OPTIONAL) - NEW: FIX 1
        if self.redirect_map_file.exists():
            print(f"  ✓ Loading {self.redirect_map_file.name} (OPTIONAL)...")
            with open(self.redirect_map_file, 'r', encoding='utf-8') as f:
                self.redirect_map = json.load(f)
            print(f"    Loaded {len(self.redirect_map)} redirect mappings")
        else:
            print(f"  ⚠ {self.redirect_map_file.name} not found (OPTIONAL)")
            print(f"    → URL resolution will use original URLs")
        
        print()
        print("Data loading complete.\n")
    
    def detect_content_type(self, url: str, page: Dict) -> str:
        """
        Detect content type based on URL patterns and page data.
        
        Args:
            url: Page URL
            page: Page data
            
        Returns:
            Content type string
        """
        url_lower = url.lower()
        page_type = page.get('page_type', 'content')
        
        # Check URL patterns
        if '/docs/' in url_lower or page_type == 'documentation':
            return 'docs'
        elif re.search(r'/(legal|privacy|terms|cookie)', url_lower):
            return 'legal'
        elif re.search(r'/(glossary|dictionary|definitions)', url_lower):
            return 'glossary'
        elif re.search(r'/(api|reference)', url_lower) or page_type == 'api_reference':
            return 'api_reference'
        else:
            return 'content'
    
    def detect_page_intent(self, url: str, page: Dict, word_count: int) -> str:
        """NEW: FIX 3 - Detect page intent for context-aware scoring
        
        Args:
            url: Page URL
            page: Page data
            word_count: Word count
            
        Returns:
            Intent: article | hub | reference | index | utility
        """
        url_lower = url.lower()
        
        # Index/hub pages (intentionally thin navigation)
        if re.search(r'/(index|guides?|reference)/?$', url_lower):
            return 'index'
        
        # Hub pages (overview/landing)
        if word_count < 500 and re.search(r'/(docs|web|api)/?$', url_lower):
            return 'hub'
        
        # Reference pages (spec/API listings)
        if re.search(r'/(elements|attributes|properties|selectors|at-rules|values)', url_lower):
            return 'reference'
        
        # Utility pages (legal, privacy, etc.)
        if re.search(r'/(legal|privacy|terms|about|contact)', url_lower):
            return 'utility'
        
        # Default: article (full content)
        return 'article'
    
    def calculate_word_score(self, word_count: int, content_type: str) -> float:
        """
        Calculate word count score based on content type.
        
        Args:
            word_count: Word count
            content_type: Content type
            
        Returns:
            Score from 0.0 to 1.0
        """
        threshold = CONFIG['word_count_thresholds'].get(content_type, 600)
        
        if word_count >= threshold * 2:
            return 1.0
        elif word_count >= threshold:
            return 0.7 + (word_count - threshold) / (threshold * 2) * 0.3
        elif word_count >= threshold * 0.5:
            return 0.4 + (word_count - threshold * 0.5) / (threshold * 0.5) * 0.3
        else:
            return min(0.4, word_count / (threshold * 0.5) * 0.4)
    
    def extract_headings_from_html(self, page: Dict) -> Tuple[int, int, int]:
        """NEW: FIX 2 - Extract heading counts from raw HTML
        
        Args:
            page: Page data
            
        Returns:
            Tuple of (h1_count, h2_count, h3_count)
        """
        # Try to get from page data first
        h1_count = page.get('h1_count', 0)
        h2_count = page.get('h2_count', 0)
        h3_count = page.get('h3_count', 0)
        
        # If all zero, try to extract from raw_html
        if h1_count == 0 and h2_count == 0 and h3_count == 0:
            raw_html = page.get('raw_html', '')
            if raw_html:
                # Simple regex extraction (not perfect but better than 0)
                h1_count = len(re.findall(r'<h1[^>]*>', raw_html, re.IGNORECASE))
                h2_count = len(re.findall(r'<h2[^>]*>', raw_html, re.IGNORECASE))
                h3_count = len(re.findall(r'<h3[^>]*>', raw_html, re.IGNORECASE))
        
        return h1_count, h2_count, h3_count
    
    def analyze_heading_structure(self, page: Dict, word_count: int) -> Dict:
        """
        Analyze heading structure quality.
        
        Args:
            page: Page data
            word_count: Word count
            
        Returns:
            Dictionary with heading analysis
        """
        # NEW: FIX 2 - Extract headings from HTML if needed
        h1_count, h2_count, h3_count = self.extract_headings_from_html(page)
        
        # Calculate expected heading counts based on word count
        words_in_thousands = word_count / 1000.0
        expected_h2 = CONFIG['expected_h2_per_1000_words'] * words_in_thousands
        expected_h3 = CONFIG['expected_h3_per_1000_words'] * words_in_thousands
        
        # Heading depth score
        score = 0.0
        
        # H1 check (exactly 1 is ideal)
        if h1_count == 1:
            score += 0.3
        elif h1_count == 0:
            score += 0.0
        else:
            score += 0.1  # Multiple H1s is suboptimal
        
        # H2/H3 structure check
        if expected_h2 > 0:
            h2_ratio = min(1.0, h2_count / expected_h2)
            score += h2_ratio * 0.4
        else:
            score += 0.2 if h2_count > 0 else 0.0
        
        if expected_h3 > 0:
            h3_ratio = min(1.0, h3_count / expected_h3)
            score += h3_ratio * 0.3
        else:
            score += 0.1 if h3_count > 0 else 0.0
        
        return {
            "h1_count": h1_count,
            "h2_count": h2_count,
            "h3_count": h3_count,
            "heading_depth_score": round(min(score, 1.0), 2)
        }
    
    def calculate_internal_authority_score(self, inlinks: int, is_cluster_leader: bool = False) -> Tuple[float, bool]:
        """
        Calculate internal authority score.
        
        BLOCKER 3: Added derived authority fallback for cluster leaders
        
        Args:
            inlinks: Number of internal links
            is_cluster_leader: Whether page is cluster leader
            
        Returns:
            Tuple of (score, is_hub)
        """
        # Normalize inlinks to 0-1 scale
        if inlinks >= CONFIG['high_authority_inlinks']:
            score = 1.0
            is_hub = True
        elif inlinks >= CONFIG['medium_authority_inlinks']:
            score = 0.5 + (inlinks - CONFIG['medium_authority_inlinks']) / \
                    (CONFIG['high_authority_inlinks'] - CONFIG['medium_authority_inlinks']) * 0.5
            is_hub = False
        elif inlinks > 0:
            score = inlinks / CONFIG['medium_authority_inlinks'] * 0.5
            is_hub = False
        else:
            score = 0.0
            is_hub = False
        
        # BLOCKER 3: Derived authority fallback for cluster leaders
        # If no inlinks but is cluster leader, assign minimum authority
        if inlinks == 0 and is_cluster_leader:
            score = max(score, 0.3)  # Cluster leaders are inherently authoritative
        
        return round(score, 2), is_hub
    
    def calculate_cluster_role_score(self, cluster_info: Dict) -> float:
        """
        Calculate cluster role score.
        
        IMPROVEMENT 2: Cluster size normalization
        - Leader of large cluster (≥5) → bonus
        - Cluster size 1 → neutral
        - Non-leader in large cluster → slight penalty
        
        Args:
            cluster_info: Cluster information
            
        Returns:
            Cluster role score (0.0-1.0)
        """
        if not cluster_info:
            return 0.5  # Neutral
        
        is_leader = cluster_info.get('is_cluster_leader', False)
        cluster_size = cluster_info.get('cluster_size', 1)
        
        # IMPROVEMENT 2: Cluster size normalization
        if is_leader:
            # Leader bonus scales with cluster size
            if cluster_size >= 5:
                return 1.0  # Strong pillar page
            elif cluster_size >= 3:
                return 0.85  # Good hub page
            elif cluster_size >= 2:
                return 0.7  # Small cluster leader
            else:
                return 0.6  # Single-page cluster (neutral-ish)
        else:
            # Non-leader penalty scales with cluster size
            if cluster_size >= 5:
                return 0.3  # Supporting page in large cluster
            elif cluster_size >= 3:
                return 0.4  # Supporting page in medium cluster
            else:
                return 0.5  # Neutral3
    
    def calculate_content_depth_score(self, word_score: float, heading_score: float,
                                     word_count: int) -> float:
        """
        Calculate composite content depth score.
        
        Args:
            word_score: Word count score
            heading_score: Heading structure score
            word_count: Raw word count
            
        Returns:
            Depth score from 0.0 to 1.0
        """
        # Semantic density proxy (simple heuristic based on word count)
        semantic_density = min(1.0, word_count / 2000.0)
        
        depth_score = (
            word_score * 0.4 +
            heading_score * 0.3 +
            semantic_density * 0.3
        )
        
        return round(depth_score, 2)
    
    def calculate_quality_score(self, depth_score: float, authority_score: float,
                               cluster_role_score: float, page_intent: str) -> float:
        """NEW: FIX 4 - Calculate final quality score with normalized components
        
        Args:
            depth_score: Content depth score
            authority_score: Internal authority score
            cluster_role_score: Cluster role score
            page_intent: Page intent (article/hub/reference/index/utility)
            
        Returns:
            Quality score from 0.0 to 1.0
        """
        # FIX 4: Normalize authority to prevent total collapse
        # If authority is 0, give minimum viable score instead of 0
        normalized_authority = max(authority_score, 0.2) if page_intent in ['hub', 'index'] else authority_score
        
        # FIX 4: Adjust weights based on intent
        if page_intent in ['hub', 'index', 'reference']:
            # For hub/index pages, reduce authority weight, increase depth
            quality_score = (
                depth_score * 0.6 +
                normalized_authority * 0.2 +
                cluster_role_score * 0.2
            )
        else:
            # For articles, standard weighting
            quality_score = (
                depth_score * 0.5 +
                authority_score * 0.3 +
                cluster_role_score * 0.2
            )
        
        return round(quality_score, 2)
    
    def assign_quality_grade(self, quality_score: float) -> str:
        """
        Assign quality grade based on score.
        
        Args:
            quality_score: Quality score
            
        Returns:
            Grade (A/B/C/D)
        """
        if quality_score >= CONFIG['grade_thresholds']['A']:
            return 'A'
        elif quality_score >= CONFIG['grade_thresholds']['B']:
            return 'B'
        elif quality_score >= CONFIG['grade_thresholds']['C']:
            return 'C'
        else:
            return 'D'
    
    def determine_ranking_potential(self, quality_score: float, is_indexable: bool,
                                   seo_eligible: bool, inlinks: int, word_count: int,
                                   content_type: str, is_cluster_leader: bool = False) -> Tuple[str, List[Dict]]:
        """BLOCKER 1: Weighted ranking potential (authority upgrades, doesn't block)
        
        Args:
            quality_score: Quality score
            is_indexable: Whether page is indexable
            seo_eligible: Whether page is SEO eligible
            inlinks: Number of internal links
            word_count: Word count
            content_type: Content type
            is_cluster_leader: Whether page is cluster leader
            
        Returns:
            Tuple of (ranking_potential, structured_blockers)
        """
        blockers = []
        
        # Check blockers (only hard blockers)
        if not is_indexable:
            blockers.append("not_indexable")
        if not seo_eligible:
            blockers.append("not_seo_eligible")
        
        # BLOCKER 1: Weighted decision - authority upgrades, doesn't block
        # Quality-driven logic: high quality can achieve HIGH even without authority
        
        # Hard blockers prevent any ranking
        if blockers:
            return "LOW", self._build_structured_blockers(blockers)
        
        # HIGH: Exceptional quality (even without strong authority)
        if quality_score >= 0.8:
            # Authority can upgrade to HIGH, but not required
            if inlinks >= CONFIG['high_authority_inlinks'] or is_cluster_leader:
                return "HIGH", []
            else:
                return "HIGH", []  # Quality alone is enough
        
        # MEDIUM: Good quality + sufficient content
        if quality_score >= 0.65:
            threshold = CONFIG['word_count_thresholds'].get(content_type, 600)
            if word_count >= threshold:
                return "MEDIUM", []
            elif quality_score >= 0.6:
                return "MEDIUM", []
            else:
                return "LOW", self._build_structured_blockers(["insufficient_content_depth"])
        
        # MEDIUM: Decent quality
        if quality_score >= 0.6:
            return "MEDIUM", []
        
        # LOW: Everything else
        return "LOW", self._build_structured_blockers(["low_quality_score"])
    
    def _build_structured_blockers(self, blocker_codes: List[str]) -> List[Dict]:
        """IMPROVEMENT 3: Build structured ranking blockers with severity and fixes
        
        Args:
            blocker_codes: List of blocker code strings
            
        Returns:
            List of structured blocker dictionaries
        """
        blocker_details = {
            "not_indexable": {
                "severity": "critical",
                "fix": "Remove noindex tag or fix indexability issues"
            },
            "not_seo_eligible": {
                "severity": "high",
                "fix": "Improve content quality or remove SEO exclusions"
            },
            "low_quality_score": {
                "severity": "medium",
                "fix": "Improve content depth, add headings, increase word count"
            },
            "insufficient_content_depth": {
                "severity": "medium",
                "fix": "Expand content to meet minimum word count threshold"
            }
        }
        
        structured_blockers = []
        for code in blocker_codes:
            details = blocker_details.get(code, {"severity": "low", "fix": "Review manually"})
            structured_blockers.append({
                "blocker": code,
                "severity": details["severity"],
                "fix": details["fix"]
            })
        
        return structured_blockers
    
    def classify_c_grade(self, quality_score: float, word_count: int, 
                        is_cluster_leader: bool, cluster_size: int,
                        page_intent: str, inlinks: int) -> str:
        """STRATEGIC 1: C-grade subclassification
        
        C1 – Fixable (expand / optimize)
        C2 – Support-only (acceptable)
        C3 – Merge / consolidate
        
        Args:
            quality_score: Quality score
            word_count: Word count
            is_cluster_leader: Whether page is cluster leader
            cluster_size: Cluster size
            page_intent: Page intent
            inlinks: Internal links
            
        Returns:
            C-grade subclass: C1, C2, or C3
        """
        # C1: Fixable - good foundation, needs expansion
        if quality_score >= 0.55 and word_count >= 300:
            return "C1"  # Has potential, expand content
        
        # C1: Fixable - cluster leader that needs strengthening
        if is_cluster_leader and cluster_size >= 3:
            return "C1"  # Important hub, must improve
        
        # C2: Support-only - acceptable by design
        if page_intent in ['utility', 'index', 'hub']:
            return "C2"  # Thin by design, acceptable
        
        # C2: Support-only - supporting page in large cluster
        if not is_cluster_leader and cluster_size >= 5:
            return "C2"  # Supporting page, acceptable
        
        # C3: Merge/consolidate - low quality, low value
        if word_count < 200 and inlinks == 0:
            return "C3"  # Orphan thin page, consider merging
        
        # C3: Merge/consolidate - duplicate or redundant
        if not is_cluster_leader and cluster_size >= 2 and word_count < 300:
            return "C3"  # Potential duplicate, consolidate
        
        # Default: C2 (support-only)
        return "C2"
    
    def determine_recommended_action(self, quality_grade: str, c_subclass: str,
                                    ranking_potential: str, is_cluster_leader: bool,
                                    page_intent: str, word_count: int,
                                    is_indexable: bool, depth_score: float) -> str:
        """STRATEGIC 2: Explicit recommended action decision path
        
        REFINEMENT 3: Added 'maintain' action for high-depth C1 pages
        
        Actions: ignore | improve | merge | expand | maintain | consolidate
        
        Args:
            quality_grade: Quality grade
            c_subclass: C-grade subclass (if applicable)
            ranking_potential: Ranking potential
            is_cluster_leader: Whether page is cluster leader
            page_intent: Page intent
            word_count: Word count
            is_indexable: Whether page is indexable
            depth_score: Content depth score
            
        Returns:
            Recommended action
        """
        # A/B grades: ignore (already good)
        if quality_grade in ['A', 'B']:
            return "ignore"  # Already high quality
        
        # D grade: merge or consolidate
        if quality_grade == 'D':
            if is_cluster_leader:
                return "improve"  # Leader must be improved
            elif word_count < 150:
                return "merge"  # Too thin, merge into parent
            else:
                return "consolidate"  # Combine with similar pages
        
        # C grade: depends on subclass
        if quality_grade == 'C':
            if c_subclass == 'C1':
                # REFINEMENT 3: Add 'maintain' for high-depth C1 pages
                if depth_score >= 0.85:
                    return "maintain"  # Good depth, just maintain quality
                # REFINEMENT 4: Less aggressive expansion for reference pages
                elif page_intent in ['reference', 'index']:
                    return "maintain"  # Reference pages, maintain current depth
                else:
                    return "expand"  # Fixable, expand content
            elif c_subclass == 'C2':
                return "ignore"  # Support-only, acceptable by design
            elif c_subclass == 'C3':
                return "consolidate"  # Merge/consolidate
        
        # Non-indexable: improve indexability first
        if not is_indexable:
            return "improve"
        
        # Default: improve
        return "improve"
    
    def build_ranking_rationale(self, quality_score: float, ranking_potential: str,
                               authority_score: float, cluster_role_score: float,
                               is_cluster_leader: bool, inlinks: int,
                               word_count: int, content_type: str) -> List[str]:
        """STRATEGIC 3: Explain ranking potential decision
        
        Args:
            quality_score: Quality score
            ranking_potential: Ranking potential
            authority_score: Authority score
            cluster_role_score: Cluster role score
            is_cluster_leader: Whether page is cluster leader
            inlinks: Internal links
            word_count: Word count
            content_type: Content type
            
        Returns:
            List of rationale statements
        """
        rationale = []
        
        # Quality assessment
        if quality_score >= 0.8:
            rationale.append("Exceptional content quality")
        elif quality_score >= 0.65:
            rationale.append("Good content depth")
        elif quality_score >= 0.5:
            rationale.append("Moderate content quality")
        else:
            rationale.append("Low content quality")
        
        # Authority assessment
        if authority_score >= 0.7:
            rationale.append("Strong internal authority")
        elif authority_score >= 0.3:
            rationale.append("Moderate internal authority")
        else:
            rationale.append("Low internal authority")
        
        # Cluster role assessment
        if is_cluster_leader:
            if cluster_role_score >= 0.85:
                rationale.append("Leader of large cluster (pillar page)")
            elif cluster_role_score >= 0.7:
                rationale.append("Leader of medium cluster (hub page)")
            else:
                rationale.append("Leader of small cluster")
        else:
            if cluster_role_score <= 0.4:
                rationale.append("Supporting page in cluster")
        
        # Content depth assessment
        threshold = CONFIG['word_count_thresholds'].get(content_type, 600)
        if word_count >= threshold * 1.5:
            rationale.append("Comprehensive content depth")
        elif word_count >= threshold:
            rationale.append("Sufficient content depth")
        else:
            rationale.append("Below recommended word count")
        
        # Inlinks assessment
        if inlinks == 0:
            rationale.append("No internal links (orphan)")
        elif inlinks < 3:
            rationale.append("Few internal links")
        
        return rationale
    
    def calculate_priority(self, quality_grade: str, ranking_potential: str,
                          is_cluster_leader: bool, is_indexable: bool,
                          c_subclass: str, cluster_size: int) -> str:
        """STRATEGIC 4: Priority tagging for fixes
        
        Priority: critical | high | medium | low
        
        Args:
            quality_grade: Quality grade
            ranking_potential: Ranking potential
            is_cluster_leader: Whether page is cluster leader
            is_indexable: Whether page is indexable
            c_subclass: C-grade subclass
            cluster_size: Cluster size
            
        Returns:
            Priority level
        """
        # CRITICAL: Weak cluster leaders of large clusters
        if is_cluster_leader and cluster_size >= 5 and quality_grade in ['C', 'D']:
            return "critical"
        
        # CRITICAL: Indexable + HIGH potential but low quality
        if is_indexable and ranking_potential == 'HIGH' and quality_grade in ['C', 'D']:
            return "critical"
        
        # HIGH: Cluster leaders that need improvement
        if is_cluster_leader and quality_grade in ['C', 'D']:
            return "high"
        
        # HIGH: Indexable + MEDIUM potential with fixable issues
        if is_indexable and ranking_potential == 'MEDIUM' and c_subclass == 'C1':
            return "high"
        
        # MEDIUM: Fixable C1 pages
        if c_subclass == 'C1':
            return "medium"
        
        # MEDIUM: D-grade pages that are indexable
        if quality_grade == 'D' and is_indexable:
            return "medium"
        
        # LOW: Everything else
        return "low"
    
    def analyze(self):
        """Run the complete content quality analysis."""
        print("Analyzing content quality...\n")
        
        for page in self.pages:
            url = page['url']
            
            # Get indexability info
            indexability = self.url_to_indexability.get(url, {})
            is_indexable = indexability.get('indexable', False)
            seo_eligible = indexability.get('seo_eligible', False)
            
            # Skip non-indexable pages (optional - analyze all for completeness)
            # if not is_indexable:
            #     continue
            
            # Detect content type
            content_type = self.detect_content_type(url, page)
            
            # Get word count
            word_count = page.get('word_count_main', page.get('word_count_raw', 0))
            reading_time = round(word_count / CONFIG['reading_speed_wpm'], 1)
            
            # NEW: FIX 3 - Detect page intent
            page_intent = self.detect_page_intent(url, page, word_count)
            
            # Calculate word score
            word_score = self.calculate_word_score(word_count, content_type)
            
            # Analyze heading structure
            heading_structure = self.analyze_heading_structure(page, word_count)
            
            # Get cluster context FIRST (before using it)
            cluster = self.url_to_cluster.get(url)
            cluster_info = None
            cluster_role_score = 0.5
            is_leader = False  # Default
            
            if cluster:
                is_leader = (url == cluster.get('canonical_leader'))
                cluster_size = len(cluster.get('members', []))
                cluster_info = {
                    "cluster_id": cluster.get('cluster_id'),
                    "is_cluster_leader": is_leader,
                    "cluster_size": cluster_size
                }
                cluster_role_score = self.calculate_cluster_role_score(cluster_info)
            
            # Get internal authority - BLOCKER 3: Pass is_cluster_leader
            inlinks = self.url_to_inlinks.get(url, 0)
            authority_score, is_hub = self.calculate_internal_authority_score(inlinks, is_leader)
            
            # Calculate content depth score
            depth_score = self.calculate_content_depth_score(
                word_score, heading_structure['heading_depth_score'], word_count
            )
            
            # Determine thin content reason - FIX 3: Adjust for intent
            threshold = CONFIG['word_count_thresholds'].get(content_type, 600)
            thin_reason = None
            # Don't flag hub/index pages as thin
            if word_count < threshold and page_intent not in ['hub', 'index', 'utility']:
                thin_reason = f"below_{content_type}_threshold_{threshold}"
            
            # Calculate final quality score - FIX 4: Pass page_intent
            quality_score = self.calculate_quality_score(
                depth_score, authority_score, cluster_role_score, page_intent
            )
            
            # Assign grade - BLOCKER 2: Cluster leader bonus
            quality_grade = self.assign_quality_grade(quality_score)
            # BLOCKER 2 Option B: Cluster leader bonus for A-grade
            if is_leader and quality_score >= 0.78:
                quality_grade = "A"
            
            # Determine ranking potential - BLOCKER 1: Pass is_cluster_leader
            ranking_potential, ranking_blockers = self.determine_ranking_potential(
                quality_score, is_indexable, seo_eligible, inlinks, word_count, content_type, is_leader
            )
            
            # STRATEGIC 1: C-grade subclassification
            c_subclass = None
            if quality_grade == 'C':
                c_subclass = self.classify_c_grade(
                    quality_score, word_count, is_leader, 
                    cluster_info.get('cluster_size', 1) if cluster_info else 1,
                    page_intent, inlinks
                )
            
            # STRATEGIC 2: Determine recommended action
            recommended_action = self.determine_recommended_action(
                quality_grade, c_subclass or 'C2', ranking_potential,
                is_leader, page_intent, word_count, is_indexable, depth_score
            )
            
            # STRATEGIC 3: Build ranking rationale
            ranking_rationale = self.build_ranking_rationale(
                quality_score, ranking_potential, authority_score,
                cluster_role_score, is_leader, inlinks, word_count, content_type
            )
            
            # STRATEGIC 4: Calculate priority
            priority = self.calculate_priority(
                quality_grade, ranking_potential, is_leader, is_indexable,
                c_subclass or 'C2', cluster_info.get('cluster_size', 1) if cluster_info else 1
            )
            
            # Build quality page entry
            quality_page = {
                "url": url,
                "is_indexable": is_indexable,
                "seo_eligible": seo_eligible,
                "content_type": content_type,
                "page_intent": page_intent,  # NEW: FIX 3
                "word_count": word_count,

                "reading_time_minutes": reading_time,
                "heading_structure": heading_structure,
                "content_depth": {
                    "depth_score": depth_score,
                    "thin_reason": thin_reason
                },
                "internal_authority": {
                    "inlinks": inlinks,
                    "link_score": authority_score,
                    "is_hub": is_hub
                },
                "cluster_context": cluster_info,
                "quality_score": quality_score,
                "quality_grade": quality_grade,
                "c_subclass": c_subclass,  # STRATEGIC 1
                "ranking_potential": ranking_potential,
                "ranking_blockers": ranking_blockers,
                "ranking_rationale": ranking_rationale,  # STRATEGIC 3
                "recommended_action": recommended_action,  # STRATEGIC 2
                "priority": priority  # STRATEGIC 4
            }
            
            self.quality_pages.append(quality_page)
        
        print(f"Analyzed {len(self.quality_pages)} pages\n")
    
    def detect_issues(self):
        """Detect content quality issues."""
        print("Detecting content quality issues...")
        
        issues = []
        issue_id = 1
        
        for page in self.quality_pages:
            url = page['url']
            word_count = page['word_count']
            content_type = page['content_type']
            inlinks = page['internal_authority']['inlinks']
            quality_score = page['quality_score']
            cluster_info = page['cluster_context']
            heading_structure = page['heading_structure']
            
            threshold = CONFIG['word_count_thresholds'].get(content_type, 600)
            
            # Issue 1: Thin content + high internal links
            if word_count < threshold and inlinks > 10:
                issues.append({
                    "issue_id": f"CQ_{issue_id:03d}",
                    "url": url,
                    "issue_type": "thin_content",
                    "severity": "high",
                    "impact": "low_ranking_potential",
                    "details": f"Page has {word_count} words (threshold: {threshold}) but receives {inlinks} internal links",
                    "recommended_action": f"Expand to {threshold * 2}+ words with structured sections"
                })
                issue_id += 1
            
            # Issue 2: Cluster leader with weak content - FIX 3: Exclude hub/index pages
            if cluster_info and cluster_info['is_cluster_leader'] and quality_score < 0.5:
                page_intent = page.get('page_intent', 'article')
                # Don't flag hub/index pages as weak leaders
                if page_intent not in ['hub', 'index']:
                    issues.append({
                        "issue_id": f"CQ_{issue_id:03d}",
                        "url": url,
                        "issue_type": "weak_cluster_leader",
                        "severity": "critical",
                        "impact": "indexation_loss",
                        "details": f"Cluster leader (size: {cluster_info['cluster_size']}) has quality score {quality_score}",
                        "recommended_action": "Improve content quality or reassign cluster leadership"
                    })
                    issue_id += 1
            
            # Issue 3: Over-optimized heading structure - REFINEMENT 1: Intent-aware thresholds
            page_intent = page.get('page_intent', 'article')
            thresholds = CONFIG['heading_thresholds'].get(page_intent, CONFIG['heading_thresholds']['article'])
            
            if heading_structure['h2_count'] > thresholds['h2_max'] or heading_structure['h3_count'] > thresholds['h3_max']:
                issues.append({
                    "issue_id": f"CQ_{issue_id:03d}",
                    "url": url,
                    "issue_type": "over_optimized_headings",
                    "severity": "medium",
                    "impact": "crawl_budget_waste",
                    "details": f"Excessive headings for {page_intent}: H2={heading_structure['h2_count']} (max: {thresholds['h2_max']}), H3={heading_structure['h3_count']} (max: {thresholds['h3_max']})",
                    "recommended_action": "Consolidate heading structure for better readability"
                })
                issue_id += 1
            
            # Issue 4: Deep content with no internal links
            if quality_score > 0.7 and inlinks == 0:
                issues.append({
                    "issue_id": f"CQ_{issue_id:03d}",
                    "url": url,
                    "issue_type": "orphaned_quality_content",
                    "severity": "medium",
                    "impact": "low_ranking_potential",
                    "details": f"High-quality content (score: {quality_score}) has no internal links",
                    "recommended_action": "Add internal links from relevant hub pages"
                })
                issue_id += 1
        
        self.quality_issues = issues
        print(f"  Detected {len(self.quality_issues)} issues\n")
    
    def generate_summary(self):
        """Generate content quality summary."""
        print("Generating content quality summary...")
        
        total_pages = len(self.quality_pages)
        
        # Quality distribution
        quality_distribution = defaultdict(int)
        for page in self.quality_pages:
            quality_distribution[page['quality_grade']] += 1
        
        # Ranking potential distribution
        ranking_distribution = defaultdict(int)
        for page in self.quality_pages:
            ranking_distribution[page['ranking_potential']] += 1
        
        # Top optimization opportunities
        opportunities = []
        
        # Thin but highly linked pages
        thin_linked = sum(1 for p in self.quality_pages 
                         if p['content_depth']['thin_reason'] and p['internal_authority']['inlinks'] > 10)
        if thin_linked > 0:
            opportunities.append(f"Improve {thin_linked} thin but highly linked pages")
        
        # Weak cluster leaders
        weak_leaders = sum(1 for p in self.quality_pages 
                          if p['cluster_context'] and p['cluster_context']['is_cluster_leader'] 
                          and p['quality_score'] < 0.6)
        if weak_leaders > 0:
            opportunities.append(f"Strengthen {weak_leaders} weak cluster leaders")
        
        # Orphaned quality content
        orphaned_quality = sum(1 for p in self.quality_pages 
                              if p['quality_score'] > 0.7 and p['internal_authority']['inlinks'] == 0)
        if orphaned_quality > 0:
            opportunities.append(f"Add internal links to {orphaned_quality} orphaned quality pages")
        
        self.quality_summary = {
            "total_pages_analyzed": total_pages,
            "quality_distribution": dict(quality_distribution),
            "ranking_potential_distribution": dict(ranking_distribution),
            "top_optimization_opportunities": opportunities
        }
        
        print(f"  Summary generated\n")
    
    def write_outputs(self):
        """Write all output files."""
        print("Writing output files...")
        
        # Ensure output directory exists
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Derive base name
        base_name = self.pages_file.stem.replace("_pages", "")
        
        # Write content_quality_pages.json
        output_file = self.output_dir / f"{base_name}_content_quality_pages.json"
        print(f"  Writing {output_file.name}...")
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(self.quality_pages, f, indent=2, ensure_ascii=False)
        print(f"    Wrote {len(self.quality_pages)} pages")
        
        # Write content_quality_issues.json
        output_file = self.output_dir / f"{base_name}_content_quality_issues.json"
        print(f"  Writing {output_file.name}...")
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(self.quality_issues, f, indent=2, ensure_ascii=False)
        print(f"    Wrote {len(self.quality_issues)} issues")
        
        # Write content_quality_summary.json
        output_file = self.output_dir / f"{base_name}_content_quality_summary.json"
        print(f"  Writing {output_file.name}...")
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(self.quality_summary, f, indent=2, ensure_ascii=False)
        
        print("\nOutput files written successfully!")
    
    def run(self):
        """Run the complete analysis pipeline."""
        self.load_data()
        self.analyze()
        self.detect_issues()
        self.generate_summary()
        self.write_outputs()


def main():
    """Main entry point."""
    import sys
    
    # Check if paths provided via command line
    if len(sys.argv) >= 2:
        pages_file = sys.argv[1]
        output_dir = sys.argv[2] if len(sys.argv) > 2 else None
    else:
        # Interactive mode
        print("=" * 70)
        print("📊 CONTENT QUALITY ANALYZER")
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
    print("📊 CONTENT QUALITY ANALYZER")
    print("=" * 70)
    print()
    
    analyzer = ContentQualityAnalyzer(pages_file, output_dir)
    analyzer.run()
    
    print("\n" + "="*70)
    print("✅ CONTENT QUALITY ANALYSIS COMPLETE")
    print("="*70)
    print(f"\n📊 Results:")
    print(f"  Total Pages: {analyzer.quality_summary['total_pages_analyzed']}")
    print(f"  Quality Distribution: {analyzer.quality_summary['quality_distribution']}")
    print(f"  Issues Found: {len(analyzer.quality_issues)}")
    print("="*70)


if __name__ == "__main__":
    main()
