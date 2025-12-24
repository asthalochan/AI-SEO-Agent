"""
Canonical Cluster Analyzer

Analyzes canonical URL clustering and consolidation for SEO audits.

## Known Limitations:

1. **Non-Crawled Variant Detection**:
   - Cannot detect URL variants that are:
     * Not internally linked
     * Not declared as canonical
     * Only referenced externally
   - Requires: Server log files or Google Search Console data
   - This is an expected limitation shared by all crawl-based tools

2. **Canonical Intent Confidence**:
   - Confidence scores are heuristic based on crawl data only
   - Requires Google indexation data, impressions, and ranking signals for perfect accuracy
   - Directionally correct but not "Google-perfect"
   - This is unavoidable without direct Google API access

## Recommended Supplements:
- Google Search Console (for indexation and external links)
- Server log files (for uncrawled variants)
- Analytics data (for user behavior signals)
"""

import json
import hashlib
import math
from typing import Dict, List, Set, Optional, Tuple
from dataclasses import dataclass, asdict, field
from pathlib import Path
from collections import defaultdict
from urllib.parse import urlparse, parse_qs
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class ClusterMember:
    """Represents a URL within a canonical cluster"""
    url: str
    normalized_url: str
    link_score: float
    content_inlinks: int
    is_indexable: bool
    status_code: int
    declared_canonical: str
    link_depth: int = 999  # NEW: Actual crawl depth from link graph


@dataclass
class CanonicalCluster:
    """Represents a canonical entity (group of URLs Google treats as one page)"""
    cluster_id: str
    canonical_leader: str
    declared_canonical: str
    initial_canonical: str = ""
    optimal_canonical: str = ""
    members: List[ClusterMember] = field(default_factory=list)
    discovered_urls: List[str] = field(default_factory=list)
    authority: Dict[str, float] = field(default_factory=dict)
    issues: List[str] = field(default_factory=list)
    canonical_violations: List[str] = field(default_factory=list)
    chain_depth: int = 0
    canonical_chain: List[str] = field(default_factory=list)
    has_canonical_loop: bool = False
    has_cross_language_canonical: bool = False
    canonical_alignment: Dict[str, any] = field(default_factory=dict)
    link_leakage_ratio: float = 0.0
    canonical_intent_confidence: float = 1.0
    confidence_level: str = "heuristic"
    confidence_explanation: str = ""  # INTEGRATION: Human-readable explanation
    crawl_coverage_limitation: bool = False
    content_fingerprint: str = ""
    internal_link_alignment: Dict[str, any] = field(default_factory=dict)
    soft_duplicates: List[str] = field(default_factory=list)
    soft_duplicate_confidence: str = "low"  # NEW: REFINEMENT C - high/medium/low
    severity: str = "low"
    fix_priority: int = 1
    seo_impact: List[str] = field(default_factory=list)
    recommended_action: str = ""
    variant_key: str = ""


class CanonicalClusterAnalyzer:
    """Analyzes canonical clustering and identifies SEO issues"""
    
    # REFINEMENT 1: Significant parameters that affect content (not just tracking)
    # These parameters should be preserved in variant keys
    SIGNIFICANT_PARAMS = {
        'lang', 'language', 'locale',  # Internationalization
        'category', 'cat', 'section',  # Content categorization
        'filter', 'sort', 'view',      # Content filtering/sorting
        'page', 'p',                   # Pagination (content-significant)
        'id', 'product_id', 'item_id'  # Entity identifiers
    }
    
    # Tracking parameters to strip (non-content-significant)
    TRACKING_PARAMS = {
        'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content',
        'ref', 'source', 'fbclid', 'gclid', 'msclkid',
        '_ga', '_gl', 'mc_cid', 'mc_eid'
    }
    
    def __init__(self, pages_json_path: str, link_graph_json_path: str, redirect_map_json_path: Optional[str] = None):
        """
        Initialize analyzer with crawler and link graph data
        
        Args:
            pages_json_path: Path to crawler pages JSON
            link_graph_json_path: Path to link graph JSON
            redirect_map_json_path: Optional path to redirect_map.json from redirect_resolver
        """
        self.pages_json_path = Path(pages_json_path)
        self.link_graph_json_path = Path(link_graph_json_path)
        self.redirect_map_json_path = Path(redirect_map_json_path) if redirect_map_json_path else None
        
        # Load data
        self.pages_data = self._load_json(self.pages_json_path)
        self.link_graph_data = self._load_json(self.link_graph_json_path)
        self.redirect_map_data = self._load_json(self.redirect_map_json_path) if self.redirect_map_json_path else None
        
        # Build lookup maps
        self.link_scores = self._build_link_score_map()
        self.pages = {page['normalized_url']: page for page in self.pages_data}  # NEW: Page lookup map
        
        # Analysis results
        self.canonical_map: Dict[str, str] = {}
        self.resolved_canonical: Dict[str, str] = {}
        self.clusters: Dict[str, CanonicalCluster] = {}
        self.external_canonicals: Set[str] = set() # To store URLs that declare an external canonical
        self.canonical_loops: Set[str] = set()  # IMPROVEMENT 2: Track canonical loops
        self.chain_paths: Dict[str, List[str]] = {}  # Track canonical chain paths
        
    def _load_json(self, path: Path) -> Dict:
        """Load JSON file"""
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def _build_link_score_map(self) -> Dict[str, Dict]:
        """Build map of URL -> link graph metrics"""
        link_map = {}
        for page in self.link_graph_data.get('pages', []):
            link_map[page['normalized_url']] = {
                'link_score': page.get('link_score', 0.0),
                'content_inlinks': page.get('content_inlinks', 0),
                'inlinks': page.get('inlinks', 0),
                'link_depth': page.get('link_depth', 999)  # NEW: Track actual crawl depth
            }
        return link_map
    
    def build_canonical_map(self):
        """Step 1: Build raw canonical map"""
        logger.info("Building canonical map...")
        
        for page in self.pages_data:
            url = page['normalized_url']
            canonical = page.get('canonical_url', url)
            
            # Normalize canonical (should already be normalized by crawler)
            # If canonical is external or missing, use self
            canonical_domain = urlparse(canonical).netloc
            page_domain = urlparse(url).netloc
            
            if canonical_domain != page_domain:
                # External canonical - flag but use self for clustering
                canonical = url
            
            self.canonical_map[url] = canonical
        
        logger.info(f"✓ Built canonical map for {len(self.canonical_map)} URLs")
    
    def resolve_canonical_chains(self):
        """Step 2: Resolve canonical chains with cycle detection (REFINED: external canonical detection)"""
        logger.info("Resolving canonical chains...")
        
        visited_global = set()
        self.chain_paths = {} # Store chain paths for each URL
        self.external_canonicals = set() # Reset for this run
        
        for start_url in self.canonical_map.keys():
            if start_url in visited_global:
                continue
            
            # DFS with cycle detection
            path = [start_url]
            visited = {start_url}
            current = start_url
            
            while True:
                canonical = self.canonical_map.get(current)
                
                if not canonical or canonical == current:
                    # Self-canonical or no canonical
                    self.resolved_canonical[start_url] = current
                    break
                
                # REFINEMENT 2: Detect external canonicals
                current_domain = urlparse(current).netloc
                canonical_domain = urlparse(canonical).netloc
                
                if current_domain != canonical_domain:
                    # External canonical - flag and stop chain
                    self.chain_paths[start_url] = path + [canonical]
                    self.external_canonicals.add(start_url)
                    self.resolved_canonical[start_url] = current # The current URL is the effective canonical within the domain
                    break
                
                if canonical in visited:
                    # IMPROVEMENT 2: Cycle/loop detected
                    path.append(canonical)
                    self.chain_paths[start_url] = path
                    self.resolved_canonical[start_url] = canonical # The canonical in the cycle is the leader
                    # Mark as having a loop
                    if not hasattr(self, 'canonical_loops'):
                        self.canonical_loops = set()
                    self.canonical_loops.add(start_url)
                    break
                
                visited.add(canonical)
                path.append(canonical)
                current = canonical
            
            # Store final path if not already stored (e.g., by external canonical detection)
            if start_url not in self.chain_paths:
                self.chain_paths[start_url] = path
            
            # Ensure resolved_canonical is set for all URLs
            if start_url not in self.resolved_canonical:
                self.resolved_canonical[start_url] = current
            
            visited_global.update(visited)
        
        # Calculate chain depths
        chain_depths = {}
        for url, path in self.chain_paths.items():
            chain_depths[url] = max(0, len(path) - 1)
        
        max_depth = max(chain_depths.values()) if chain_depths else 0
        chained_urls = sum(1 for d in chain_depths.values() if d > 0)
        
        logger.info(f"✓ Resolved {len(self.resolved_canonical)} canonical chains")
        logger.info(f"  → Max chain depth: {max_depth}")
        logger.info(f"  → URLs with chains: {chained_urls}")
    
    def _get_variant_key(self, url: str) -> str:
        """Generate variant key for clustering (REFINED: preserve significant params)"""
        parsed = urlparse(url)
        
        # Normalize path
        path = parsed.path.lower().rstrip('/')
        if not path:
            path = "/"
        
        # REFINEMENT 1: Handle query parameters intelligently
        significant_params = []
        if parsed.query:
            params = parse_qs(parsed.query)
            
            # Keep only significant parameters
            for key in sorted(params.keys()):
                if key.lower() in self.SIGNIFICANT_PARAMS:
                    # Preserve content-significant params in variant key
                    values = params[key]
                    for value in sorted(values):
                        significant_params.append(f"{key}={value}")
        
        # Build variant key
        base_key = f"{parsed.scheme}://{parsed.netloc}{path}"
        if significant_params:
            base_key += "?" + "&".join(significant_params)
        
        return base_key

    def build_clusters(self):
        """Step 3: Build canonical clusters grouping by variant key"""
        logger.info("Building canonical clusters (variant-aware)...")
        
        # Group URLs by VARIANT KEY of their final canonical
        # This merges /page and /page/ into same cluster if both are self-canonical
        cluster_groups = defaultdict(list)
        cluster_canonical_leaders = {} # variant_key -> list of resolved_canonicals mapping to it
        
        for page in self.pages_data:
            url = page['normalized_url']
            final_canonical = self.resolved_canonical.get(url, url)
            
            # Compute variant key for the RESOLVED CANONICAL
            # This ensures that if A -> B and C -> B/, both A and C end up in key(B) group
            variant_key = self._get_variant_key(final_canonical)
            
            # Get link metrics
            link_metrics = self.link_scores.get(url, {
                'link_score': 0.0,
                'content_inlinks': 0,
                'inlinks': 0,
                'link_depth': 999
            })
            
            # Use raw URL from page data or normalized if missing
            raw_url = page.get('url', url)
            
            # Create cluster member
            member = ClusterMember(
                url=raw_url,
                normalized_url=url,
                link_score=link_metrics['link_score'],
                content_inlinks=link_metrics['content_inlinks'],
                is_indexable=page.get('indexable', False),
                status_code=page.get('status_code', 0),
                declared_canonical=page.get('canonical_url', url),
                link_depth=link_metrics.get('link_depth', 999)  # NEW: Use actual depth
            )
            
            # IMPROVEMENT 4: Generate content fingerprint
            title = page.get('title', '')
            h1 = page.get('h1', '')
            if title or h1:
                import hashlib
                content_str = f"{title}|{h1}".lower().strip()
                content_hash = hashlib.md5(content_str.encode()).hexdigest()[:8]
                # Store in a map for later use
                if not hasattr(self, 'content_fingerprints'):
                    self.content_fingerprints = {}
                self.content_fingerprints[url] = content_hash
            
            cluster_groups[variant_key].append(member)
            
            # Track which canonicals map to this variant
            if variant_key not in cluster_canonical_leaders:
                cluster_canonical_leaders[variant_key] = set()
            cluster_canonical_leaders[variant_key].add(final_canonical)
        
        # Create clusters
        for variant_key, members in cluster_groups.items():
            # Initial leader is one of the resolved canonicals (pick first/shortest)
            candidates = list(cluster_canonical_leaders[variant_key])
            initial_leader = min(candidates, key=len) if candidates else variant_key
            
            cluster_id = hashlib.md5(variant_key.encode()).hexdigest()[:12]
            
            # Calculate chain depth per member, not longest cluster path
            max_depth = 0
            longest_chain = []
            for member in members:
                path = self.chain_paths.get(member.normalized_url, [])
                member_depth = max(0, len(path) - 1) if path else 0
                if member_depth > max_depth:
                    max_depth = member_depth
                    longest_chain = path
            
            # Find most common declared canonical from members
            from collections import Counter
            declared_canonicals = [m.declared_canonical for m in members]
            most_common_declared = Counter(declared_canonicals).most_common(1)[0][0] if declared_canonicals else initial_leader
            
            cluster = CanonicalCluster(
                cluster_id=cluster_id,
                canonical_leader=initial_leader,
                initial_canonical=initial_leader,  # NEW: Store initial
                declared_canonical=most_common_declared,
                members=members,
                chain_depth=max_depth,
                canonical_chain=longest_chain,
                variant_key=variant_key
            )
            
            # IMPROVEMENT 2: Detect canonical loops
            if hasattr(self, 'canonical_loops'):
                for member in members:
                    if member.normalized_url in self.canonical_loops:
                        cluster.has_canonical_loop = True
                        break
            
            # IMPROVEMENT 2: Detect cross-language canonicals
            # Check if canonical chain crosses language boundaries
            for member in members:
                chain = self.chain_paths.get(member.normalized_url, [])
                if len(chain) > 1:
                    # Simple heuristic: check for /en-US/, /fr/, /de/, etc. in path
                    lang_patterns = ['/en-us/', '/en/', '/fr/', '/de/', '/es/', '/ja/', '/zh/', '/pt/', '/it/', '/ru/']
                    member_langs = [p for p in lang_patterns if p in member.normalized_url.lower()]
                    chain_langs = [p for url in chain for p in lang_patterns if p in url.lower()]
                    if member_langs and chain_langs and member_langs[0] != chain_langs[-1]:
                        cluster.has_cross_language_canonical = True
                        break
            
            # INTEGRATION: Generate confidence explanation
            cluster.confidence_explanation = self._generate_confidence_explanation(cluster)
            
            self.clusters[variant_key] = cluster
            
            # IMPROVEMENT 4: Set content fingerprint for cluster
            if hasattr(self, 'content_fingerprints'):
                # Use fingerprint from leader or most common fingerprint
                fingerprints = [self.content_fingerprints.get(m.normalized_url, '') for m in members]
                fingerprints = [f for f in fingerprints if f]  # Remove empty
                if fingerprints:
                    from collections import Counter
                    most_common_fp = Counter(fingerprints).most_common(1)[0][0]
                    cluster.content_fingerprint = most_common_fp
        
        logger.info(f"✓ Built {len(self.clusters)} variant-grouped clusters")
        
        # IMPROVEMENT 1: Enrich clusters with discovered URLs from link graph
        self.enrich_clusters_from_link_graph()
    
    def enrich_clusters_from_link_graph(self):
        """IMPROVEMENT 1: Enrich clusters with URLs discovered in link graph but not crawled"""
        logger.info("Enriching clusters with link graph data...")
        
        enriched_count = 0
        
        try:
            # Get all crawled URLs
            crawled_urls = set(self.canonical_map.keys())
            
            # Check link graph for discovered URLs
            for page in self.link_graph_data.get('pages', []):
                url = page.get('normalized_url')
                if url and url in crawled_urls:
                    # Check outlinks for uncrawled URLs
                    outlinks = page.get('outlinks', [])
                    if isinstance(outlinks, list):
                        for link in outlinks:
                            if isinstance(link, dict):
                                link_url = link.get('target_url', '')
                                if link_url and link_url not in crawled_urls:
                                    # Find which cluster this URL would belong to
                                    try:
                                        variant_key = self._get_variant_key(link_url)
                                        if variant_key in self.clusters:
                                            if link_url not in self.clusters[variant_key].discovered_urls:
                                                self.clusters[variant_key].discovered_urls.append(link_url)
                                                enriched_count += 1
                                    except Exception:
                                        continue  # Skip malformed URLs
        except Exception as e:
            logger.warning(f"Link graph enrichment encountered error: {e}")
        
        logger.info(f"✓ Enriched clusters with {enriched_count} discovered URLs")
    
    def _generate_confidence_explanation(self, cluster: CanonicalCluster) -> str:
        """INTEGRATION: Generate human-readable confidence explanation"""
        if len(cluster.members) == 1:
            return "High confidence: single-page cluster with no conflicts"
        
        total = len(cluster.members)
        agreeing = sum(1 for m in cluster.members if m.declared_canonical == cluster.declared_canonical)
        
        if cluster.canonical_intent_confidence >= 0.8:
            return f"High confidence: {agreeing} of {total} pages agree on canonical"
        elif cluster.canonical_intent_confidence >= 0.6:
            return f"Medium confidence: {agreeing} of {total} pages agree on canonical"
        else:
            link_split = cluster.link_leakage_ratio > 0.3
            reason = "internal links are split" if link_split else "pages disagree on canonical"
            return f"Low confidence: only {agreeing} of {total} pages agree on canonical and {reason}"
    
    def select_cluster_leaders(self):
        """Step 4: Select optimal cluster leader using weighted scoring (ENHANCED: redirect > canonical precedence)"""
        logger.info("Selecting cluster leaders (redirect > canonical precedence)...")
        
        overrides = 0
        
        for cluster in self.clusters.values():
            # REFINEMENT B: Weighted leader selection
            def calculate_leader_score(member: ClusterMember) -> float:
                # Get page data from self.pages
                page_data = self.pages.get(member.normalized_url, {})
                
                # PRECEDENCE RULE 1: Check redirect_map.json first (if available)
                if self.redirect_map_data:
                    redirect_record = self.redirect_map_data.get(member.normalized_url, {})
                    final_url = redirect_record.get('final_url', member.normalized_url)
                    
                    # If URL redirects, DISQUALIFY from being canonical leader
                    if final_url != member.normalized_url:
                        return -1000  # ABSOLUTE DISQUALIFICATION
                    
                    # Also check final_status from redirect map
                    final_status = redirect_record.get('final_status', member.status_code)
                else:
                    # Fallback: use crawler data
                    final_status = page_data.get('final_status', member.status_code)
                    final_url = page_data.get('final_url', member.normalized_url)
                    
                    # Fallback redirect check
                    if member.normalized_url != final_url:
                        return -1000  # ABSOLUTE DISQUALIFICATION
                
                # CRITICAL: Discard if final_status != 200
                if final_status != 200:
                    return -1000  # Discard completely
                
                # REFINEMENT B: Weighted scoring
                # Leader score = (link_score * 0.5) + (content_inlinks * 0.3) + (indexable * 0.2)
                score = (
                    member.link_score * 0.5 +
                    member.content_inlinks * 0.3 +
                    (1.0 if member.is_indexable else 0.0) * 0.2
                )
                
                # Penalties
                if member.status_code != 200:
                    score -= 100  # Heavy penalty for non-200
                if "https" not in member.normalized_url:
                    score -= 0.05  # Slight HTTPS preference
                
                return score
            
            candidates = cluster.members
            if not candidates:
                continue
                
            best_candidate = max(candidates, key=calculate_leader_score)
            
            # NEW: Store optimal canonical separately (don't blindly overwrite)
            cluster.optimal_canonical = best_candidate.normalized_url
            
            # Only update leader if optimal differs from initial
            if cluster.optimal_canonical != cluster.initial_canonical:
                cluster.canonical_leader = cluster.optimal_canonical
                overrides += 1
            
            # REFINEMENT A: Check for redirect-canonical conflicts
            if self.redirect_map_data:
                redirect_record = self.redirect_map_data.get(cluster.canonical_leader, {})
                final_url = redirect_record.get('final_url', cluster.canonical_leader)
                
                # If canonical leader redirects, this is a conflict
                if final_url != cluster.canonical_leader:
                    if "REDIRECT_CANONICAL_CONFLICT" not in cluster.issues:
                        cluster.issues.append("REDIRECT_CANONICAL_CONFLICT")
                    # Downgrade canonical trust
                    cluster.canonical_intent_confidence *= 0.5
            
            # Check if selected leader differs from declared canonical
            if cluster.canonical_leader != cluster.declared_canonical:
                if "WRONG_CANONICAL" not in cluster.issues:
                    cluster.issues.append("WRONG_CANONICAL")
                
        logger.info(f"✓ Selected leaders (overridden/optimized: {overrides})")
    
    def analyze_canonical_alignment(self):
        """Analyze canonical alignment (FIXED: use scoring instead of strict AND)"""
        logger.info("Analyzing canonical alignment...")
        
        for cluster in self.clusters.values():
            if len(cluster.members) == 1:
                # Single-URL cluster - always aligned
                cluster.canonical_alignment = {
                    "declared": cluster.canonical_leader,
                    "most_linked": cluster.canonical_leader,
                    "shallowest": cluster.canonical_leader,
                    "is_optimal": True,
                    "alignment_score": 1.0
                }
                continue
            
            # Find most linked URL
            most_linked = max(cluster.members, key=lambda m: m.link_score)
            
            # Find shallowest URL (ENHANCED: Use actual link_depth from link graph)
            shallowest = min(cluster.members, key=lambda m: m.link_depth)
            
            # FIXED: Use scoring approach instead of strict AND
            alignment_score = (
                (cluster.canonical_leader == most_linked.normalized_url) * 0.6 +
                (cluster.canonical_leader == shallowest.normalized_url) * 0.4
            )
            is_optimal = alignment_score >= 0.6
            
            cluster.canonical_alignment = {
                "declared": cluster.canonical_leader,
                "most_linked": most_linked.normalized_url,
                "shallowest": shallowest.normalized_url,
                "is_optimal": is_optimal,
                "alignment_score": round(alignment_score, 2)
            }
            
            if not is_optimal:
                cluster.issues.append("SUBOPTIMAL_CANONICAL")
        
        logger.info("✓ Canonical alignment analyzed")
    
    def calculate_authority(self):
        """Step 5: Calculate authority consolidation and link leakage (FIXED: only when cluster > 1)"""
        logger.info("Calculating authority consolidation...")
        
        for cluster in self.clusters.values():
            # Total cluster authority
            cluster_total = sum(m.link_score for m in cluster.members)
            
            # Leader's share
            leader_member = next(
                (m for m in cluster.members if m.normalized_url == cluster.canonical_leader),
                None
            )
            
            leader_score = leader_member.link_score if leader_member else 0.0
            
            # FIXED: Only calculate leakage if cluster has multiple members
            if len(cluster.members) > 1:
                leader_share = leader_score / cluster_total if cluster_total > 0 else 0.0
                leakage = 1.0 - leader_share if cluster_total > 0 else 0.0
                
                # Calculate link leakage ratio (inlinks to non-canonical URLs)
                total_inlinks = sum(m.content_inlinks for m in cluster.members)
                leader_inlinks = leader_member.content_inlinks if leader_member else 0
                link_leakage_ratio = 1.0 - (leader_inlinks / total_inlinks) if total_inlinks > 0 else 0.0
            else:
                # Single-page cluster has no leakage
                leader_share = 1.0
                leakage = 0.0
                link_leakage_ratio = 0.0
            
            cluster.authority = {
                "cluster_total": round(cluster_total, 3),
                "leader_share": round(leader_share, 3),
                "leakage": round(leakage, 3)
            }
            
            cluster.link_leakage_ratio = round(link_leakage_ratio, 3)
            
            # REFINEMENT D: Calculate numeric canonical intent confidence (0.0-1.0)
            # Based on:
            # - % of members declaring same canonical
            # - Authority concentration
            # - Redirect alignment
            if len(cluster.members) > 1:
                # Factor 1: Member agreement (% declaring most common canonical)
                from collections import Counter
                declared_counts = Counter(m.declared_canonical for m in cluster.members)
                most_common_count = declared_counts.most_common(1)[0][1]
                member_agreement = most_common_count / len(cluster.members)
                
                # Factor 2: Authority concentration (leader share)
                authority_concentration = leader_share
                
                # Factor 3: Redirect alignment
                redirect_alignment = 1.0
                if self.redirect_map_data:
                    # Check if any members redirect away from leader
                    redirecting_members = 0
                    for member in cluster.members:
                        redirect_record = self.redirect_map_data.get(member.normalized_url, {})
                        final_url = redirect_record.get('final_url', member.normalized_url)
                        if final_url != member.normalized_url and final_url != cluster.canonical_leader:
                            redirecting_members += 1
                    redirect_alignment = 1.0 - (redirecting_members / len(cluster.members))
                
                # Calculate weighted confidence
                cluster.canonical_intent_confidence = round(
                    member_agreement * 0.5 +
                    authority_concentration * 0.3 +
                    redirect_alignment * 0.2,
                    2
                )
                
                # Set confidence level metadata (for backward compatibility)
                if cluster.canonical_intent_confidence >= 0.8:
                    cluster.confidence_level = "high"
                elif cluster.canonical_intent_confidence >= 0.6:
                    cluster.confidence_level = "medium"
                else:
                    cluster.confidence_level = "low"
                
                # Flag low confidence
                if cluster.canonical_intent_confidence < 0.6:
                    cluster.issues.append("LOW_CANONICAL_CONFIDENCE")
            else:
                cluster.canonical_intent_confidence = 1.0
                
                # IMPROVEMENT 2: Adjust confidence for single-page clusters
                # Single crawled URL ≠ single URL exists (could be crawl-limited)
                if cluster.crawl_coverage_limitation:
                    cluster.confidence_level = "medium"  # Downgraded due to crawl limits
                else:
                    cluster.confidence_level = "high"  # Single-page cluster
            
            # NEW: Flag crawl coverage limitation
            # If cluster has external canonical or only 1 member, may be missing variants
            if len(cluster.members) == 1:
                cluster.crawl_coverage_limitation = True  # May have non-crawled variants
        
        logger.info("✓ Authority calculated")
    
    def detect_issues(self):
        """Step 6: Detect canonical issues and violations (REFINED: external canonical detection)"""
        logger.info("Detecting canonical issues...")
        
        for cluster in self.clusters.values():
            leader = cluster.canonical_leader
            
            # Parse leader URL
            leader_parsed = urlparse(leader)
            leader_path = leader_parsed.path.rstrip('/')
            
            # Get leader member for checks
            leader_member = next((m for m in cluster.members if m.normalized_url == leader), None)
            
            # Check each member for issues
            for member in cluster.members:
                member_parsed = urlparse(member.url)
                member_path = member_parsed.path.rstrip('/')
                member_path_no_slash = member_path.rstrip('/')
                leader_path_no_slash = leader_path.rstrip('/')
                
                # REFINEMENT 2: External canonical detection
                if member.normalized_url in self.external_canonicals:
                    if "EXTERNAL_CANONICAL_TARGET" not in cluster.issues:
                        cluster.issues.append("EXTERNAL_CANONICAL_TARGET")
                        cluster.canonical_violations.append("points_to_external_domain")
                
                # Canonical to homepage
                # Check if declared canonical is just the domain (homepage) and it's not the member itself
                declared_canonical_parsed = urlparse(member.declared_canonical)
                if declared_canonical_parsed.path.rstrip('/') == '' and declared_canonical_parsed.netloc == member_parsed.netloc:
                    if member.normalized_url != member.declared_canonical: # Only flag if it's not self-canonical to homepage
                        if "CANONICAL_TO_HOMEPAGE" not in cluster.issues:
                            cluster.issues.append("CANONICAL_TO_HOMEPAGE")
                            cluster.canonical_violations.append("points_to_homepage")
                
                # Canonical to non-indexable
                if leader_member and not leader_member.is_indexable:
                    if "CANONICAL_TO_NON_INDEXABLE" not in cluster.issues:
                        cluster.issues.append("CANONICAL_TO_NON_INDEXABLE")
                        cluster.canonical_violations.append("points_to_noindex")
                
                # Canonical to non-200
                if leader_member and leader_member.status_code != 200:
                    if "CANONICAL_TO_ERROR_PAGE" not in cluster.issues:
                        cluster.issues.append("CANONICAL_TO_ERROR_PAGE")
                        cluster.canonical_violations.append("points_to_non_200")
                
                # Canonical chains
                chain = self.chain_paths.get(member.normalized_url, [])
                if len(chain) > 2:  # More than just URL -> canonical
                    if "CANONICAL_CHAIN" not in cluster.issues:
                        cluster.issues.append("CANONICAL_CHAIN")
                
                # IMPLICIT CONFLICTS (variant detection)
                # TRAILING_SLASH_VARIANT
                if member_path_no_slash == leader_path_no_slash:
                    # Bases match
                    if member_parsed.path != leader_parsed.path:
                         if "TRAILING_SLASH_VARIANT" not in cluster.issues:
                            cluster.issues.append("TRAILING_SLASH_VARIANT")
                
                # PARAMETER_VARIANT
                if "?" in member.url:
                     if "PARAMETER_VARIANT" not in cluster.issues:
                        cluster.issues.append("PARAMETER_VARIANT")
                
                # CASE_VARIANT
                # already handled by variant grouping mostly but check
                if member_parsed.path.lower() == leader_parsed.path.lower() and member_parsed.path != leader_parsed.path:
                     if "CASE_VARIANT" not in cluster.issues:
                        cluster.issues.append("CASE_VARIANT")
            
            # IMPROVEMENT 2: Flag canonical loops
            if cluster.has_canonical_loop:
                if "CANONICAL_LOOP" not in cluster.issues:
                    cluster.issues.append("CANONICAL_LOOP")
            
            # IMPROVEMENT 2: Flag cross-language canonicals
            if cluster.has_cross_language_canonical:
                if "CROSS_LANGUAGE_CANONICAL" not in cluster.issues:
                    cluster.issues.append("CROSS_LANGUAGE_CANONICAL")
            
            # IMPROVEMENT 1: Redirect-aware canonical suppression
            # Check each member for redirect + canonical combination
            for member in cluster.members:
                # Check if this URL redirects
                if self.redirect_map_data:
                    redirect_record = self.redirect_map_data.get(member.normalized_url, {})
                    final_url = redirect_record.get('final_url', member.normalized_url)
                    
                    # URL A → redirects → URL B, but URL A declares canonical → URL C
                    if final_url != member.normalized_url and member.declared_canonical:
                        # This URL redirects AND has a canonical tag
                        if "CANONICAL_IGNORED_DUE_TO_REDIRECT" not in cluster.issues:
                            cluster.issues.append("CANONICAL_IGNORED_DUE_TO_REDIRECT")
                            cluster.canonical_violations.append(f"canonical_ignored_on_{member.normalized_url}")
                        
                        # Force leader to be redirect final URL (not canonical)
                        # This is handled in select_cluster_leaders() via disqualification
                        # But we flag it here for visibility
                else:
                    # Fallback: use crawler data
                    page_data = self.pages.get(member.normalized_url, {})
                    redirect_chain = page_data.get('redirect_chain', [])
                    final_url = page_data.get('final_url', member.normalized_url)
                    
                    if redirect_chain and member.declared_canonical and final_url != member.normalized_url:
                        if "CANONICAL_IGNORED_DUE_TO_REDIRECT" not in cluster.issues:
                            cluster.issues.append("CANONICAL_IGNORED_DUE_TO_REDIRECT")
                            cluster.canonical_violations.append(f"canonical_ignored_on_{member.normalized_url}")
            
            # NEW: Redirect-aware issue detection (existing logic)
            for member in cluster.members:
                # Get page data from self.pages
                page_data = self.pages.get(member.normalized_url, {})
                
                # CANONICAL_POINTS_TO_REDIRECT: Canonical URL itself redirects
                redirect_chain = page_data.get('redirect_chain', [])
                if redirect_chain and member.normalized_url == cluster.canonical_leader:
                    if "CANONICAL_POINTS_TO_REDIRECT" not in cluster.issues:
                        cluster.issues.append("CANONICAL_POINTS_TO_REDIRECT")
                        cluster.canonical_violations.append("canonical_is_redirect")
                
                # CANONICAL_FINAL_URL_MISMATCH: Declared canonical != final URL after redirects
                final_url = page_data.get('final_url', member.normalized_url)
                if member.declared_canonical and member.declared_canonical != final_url:
                    # Check if the declared canonical is in this cluster
                    if member.declared_canonical == cluster.canonical_leader:
                        if "CANONICAL_FINAL_URL_MISMATCH" not in cluster.issues:
                            cluster.issues.append("CANONICAL_FINAL_URL_MISMATCH")
                            cluster.canonical_violations.append("canonical_final_url_mismatch")
            
            # Authority leakage
            if cluster.authority.get('leakage', 0) > 0.3:
                if "AUTHORITY_LEAKAGE" not in cluster.issues:
                    cluster.issues.append("AUTHORITY_LEAKAGE")
            
            # Link leakage
            if cluster.link_leakage_ratio > 0.3:
                if "LINK_LEAKAGE" not in cluster.issues:
                    cluster.issues.append("LINK_LEAKAGE")
        
        # IMPROVEMENT 3: Cross-cluster conflict detection
        self.detect_cross_cluster_conflicts()
        
        # ENTERPRISE 2: Internal link → canonical alignment
        self.analyze_internal_link_alignment()
        
        # ENTERPRISE 4: Content similarity for soft duplicates
        self.detect_soft_duplicates()
        
        logger.info("✓ Issues detected")
    
    def detect_cross_cluster_conflicts(self):
        """IMPROVEMENT 3: Detect conflicts across clusters"""
        logger.info("Detecting cross-cluster conflicts...")
        
        # Build map of canonical targets
        canonical_targets = defaultdict(list)
        for cluster in self.clusters.values():
            canonical_targets[cluster.canonical_leader].append(cluster.cluster_id)
        
        # Detect duplicate canonical targets
        for canonical, cluster_ids in canonical_targets.items():
            if len(cluster_ids) > 1:
                # Multiple clusters pointing to same canonical
                for cluster_id in cluster_ids:
                    cluster = next(c for c in self.clusters.values() if c.cluster_id == cluster_id)
                    if "DUPLICATE_CANONICAL_TARGET" not in cluster.issues:
                        cluster.issues.append("DUPLICATE_CANONICAL_TARGET")
        
        logger.info("✓ Cross-cluster conflicts detected")
    
    def analyze_internal_link_alignment(self):
        """ENTERPRISE 2: Analyze internal links pointing to non-canonical URLs"""
        logger.info("Analyzing internal link → canonical alignment...")
        
        total_misaligned_links = 0
        
        for cluster in self.clusters.values():
            canonical_url = cluster.canonical_leader
            non_canonical_inlinks = 0
            canonical_inlinks = 0
            
            # Count internal links to each member
            for member in cluster.members:
                if member.normalized_url == canonical_url:
                    canonical_inlinks += member.content_inlinks
                else:
                    non_canonical_inlinks += member.content_inlinks
            
            total_inlinks = canonical_inlinks + non_canonical_inlinks
            
            if total_inlinks > 0:
                misalignment_ratio = non_canonical_inlinks / total_inlinks
                
                cluster.internal_link_alignment = {
                    "canonical_inlinks": canonical_inlinks,
                    "non_canonical_inlinks": non_canonical_inlinks,
                    "total_inlinks": total_inlinks,
                    "misalignment_ratio": round(misalignment_ratio, 3),
                    "wasted_authority": non_canonical_inlinks > 0
                }
                
                # Flag significant misalignment
                if non_canonical_inlinks > 10 or misalignment_ratio > 0.3:
                    if "INTERNAL_LINK_MISALIGNMENT" not in cluster.issues:
                        cluster.issues.append("INTERNAL_LINK_MISALIGNMENT")
                        total_misaligned_links += non_canonical_inlinks
        
        logger.info(f"✓ Internal link alignment analyzed ({total_misaligned_links} misaligned links)")
    
    def detect_soft_duplicates(self):
        """REFINEMENT C: Detect soft duplicates with confidence scoring"""
        logger.info("Detecting soft duplicates via content similarity...")
        
        if not hasattr(self, 'content_fingerprints'):
            logger.info("✓ No content fingerprints available, skipping soft duplicate detection")
            return
        
        # Build fingerprint → URLs map
        fingerprint_map = defaultdict(list)
        for url, fingerprint in self.content_fingerprints.items():
            if fingerprint:
                fingerprint_map[fingerprint].append(url)
        
        # Detect duplicates
        duplicate_count = 0
        for fingerprint, urls in fingerprint_map.items():
            if len(urls) > 1:
                # Multiple URLs with same content fingerprint
                for url in urls:
                    # Find cluster for this URL
                    variant_key = self._get_variant_key(url)
                    if variant_key in self.clusters:
                        cluster = self.clusters[variant_key]
                        # Add other URLs as soft duplicates
                        other_urls = [u for u in urls if u != url]
                        cluster.soft_duplicates.extend(other_urls)
                        
                        # REFINEMENT C: Calculate soft duplicate confidence
                        cluster.soft_duplicate_confidence = self._calculate_soft_duplicate_confidence(
                            url, other_urls
                        )
                        
                        if "SOFT_DUPLICATE_CONTENT" not in cluster.issues:
                            cluster.issues.append("SOFT_DUPLICATE_CONTENT")
                            duplicate_count += 1
        
        logger.info(f"✓ Soft duplicate detection complete ({duplicate_count} clusters with duplicates)")
    
    def _calculate_soft_duplicate_confidence(self, url: str, duplicate_urls: List[str]) -> str:
        """REFINEMENT C: Calculate soft duplicate confidence (high/medium/low)
        
        Based on:
        - Word count bucket similarity
        - URL depth similarity
        """
        from urllib.parse import urlparse
        
        # Get page data
        page = self.pages.get(url, {})
        word_count = page.get('word_count_main', 0)
        url_depth = urlparse(url).path.count('/')
        
        # Calculate similarity scores
        word_count_matches = 0
        url_depth_matches = 0
        
        for dup_url in duplicate_urls:
            dup_page = self.pages.get(dup_url, {})
            dup_word_count = dup_page.get('word_count_main', 0)
            dup_url_depth = urlparse(dup_url).path.count('/')
            
            # Word count bucket similarity (within 20%)
            if word_count > 0 and dup_word_count > 0:
                ratio = min(word_count, dup_word_count) / max(word_count, dup_word_count)
                if ratio >= 0.8:
                    word_count_matches += 1
            
            # URL depth similarity (exact match)
            if url_depth == dup_url_depth:
                url_depth_matches += 1
        
        total_dups = len(duplicate_urls)
        if total_dups == 0:
            return "low"
        
        word_count_ratio = word_count_matches / total_dups
        url_depth_ratio = url_depth_matches / total_dups
        
        # Confidence scoring
        if word_count_ratio >= 0.8 and url_depth_ratio >= 0.8:
            return "high"
        elif word_count_ratio >= 0.5 or url_depth_ratio >= 0.5:
            return "medium"
        else:
            return "low"
    
    def get_summary(self) -> Dict:
        """Get summary statistics"""
        clusters_with_issues = sum(1 for c in self.clusters.values() if c.issues)
        authority_leakage_clusters = sum(
            1 for c in self.clusters.values() 
            if c.authority.get('leakage', 0) > 0.3
        )
        
        # Issue breakdown
        issue_counts = defaultdict(int)
        for cluster in self.clusters.values():
            for issue in cluster.issues:
                issue_counts[issue] += 1
        
        return {
            "total_clusters": len(self.clusters),
            "clusters_with_issues": clusters_with_issues,
            "authority_leakage_clusters": authority_leakage_clusters,
            "single_url_clusters": sum(1 for c in self.clusters.values() if len(c.members) == 1),
            "multi_url_clusters": sum(1 for c in self.clusters.values() if len(c.members) > 1),
            "issue_breakdown": dict(issue_counts)
        }
    
    def export_results(self, output_path: str):
        """Export cluster analysis to JSON"""
        output_path = Path(output_path)
        
        # Convert clusters to dict
        clusters_list = []
        for cluster in self.clusters.values():
            cluster_dict = {
                "cluster_id": cluster.cluster_id,
                "canonical_leader": cluster.canonical_leader,
                "declared_canonical": cluster.declared_canonical,
                "initial_canonical": cluster.initial_canonical,
                "optimal_canonical": cluster.optimal_canonical,
                "members": [asdict(m) for m in cluster.members],
                "discovered_urls": cluster.discovered_urls,
                "authority": cluster.authority,
                "issues": cluster.issues,
                "canonical_chain": cluster.canonical_chain,
                "canonical_alignment": cluster.canonical_alignment,
                "internal_link_alignment": cluster.internal_link_alignment,
                "variant_key": cluster.variant_key,
                "chain_depth": cluster.chain_depth,
                "canonical_intent_confidence": cluster.canonical_intent_confidence,
                "confidence_level": cluster.confidence_level,
                "confidence_explanation": cluster.confidence_explanation,
                "crawl_coverage_limitation": cluster.crawl_coverage_limitation,
                "content_fingerprint": cluster.content_fingerprint,
                "soft_duplicates": cluster.soft_duplicates,
                "soft_duplicate_confidence": cluster.soft_duplicate_confidence,  # NEW: REFINEMENT C
                "fix_priority": cluster.fix_priority,
                "severity": cluster.severity,
                "seo_impact": cluster.seo_impact,
                "recommended_action": cluster.recommended_action
            }
            clusters_list.append(cluster_dict)
        
        output_data = {
            "clusters": clusters_list,
            "summary": self.get_summary(),
                "analyzer_metadata": {
                "version": "1.0.0",
                "enterprise_features": {
                    "internal_link_alignment": {
                        "description": "Analyzes internal links pointing to non-canonical URLs",
                        "metrics": ["canonical_inlinks", "non_canonical_inlinks", "misalignment_ratio"],
                        "impact": "Identifies wasted authority from misaligned internal links"
                    },
                    "soft_duplicate_detection": {
                        "description": "Detects content duplicates using title+H1 fingerprinting",
                        "method": "MD5 hash of title|H1",
                        "impact": "Identifies parameter-based or soft duplicates"
                    },
                    "cross_cluster_conflicts": {
                        "description": "Detects multiple clusters pointing to same canonical",
                        "flag": "DUPLICATE_CANONICAL_TARGET",
                        "impact": "Catches pagination, language, and parameter canonical bugs"
                    },
                    "redirect_aware_logic": {
                        "status": "planned",
                        "description": "Canonical → redirect chain conflict detection",
                        "requires": "HTTP redirect graph from crawler"
                    },
                    "search_console_alignment": {
                        "status": "planned",
                        "description": "Compare declared vs calculated vs Google-chosen canonical",
                        "requires": "Google Search Console API integration"
                    }
                },
                "refinements": {
                    "significant_parameters": {
                        "description": "Content-significant parameters are preserved in variant keys",
                        "parameters": list(self.SIGNIFICANT_PARAMS),
                        "impact": "Better clustering for filtered/categorized content"
                    },
                    "external_canonical_detection": {
                        "description": "Detects and flags canonicals pointing to external domains",
                        "flag": "EXTERNAL_CANONICAL_TARGET",
                        "impact": "Identifies syndicated content or misconfigured canonicals"
                    },
                    "redirect_chain_integration": {
                        "description": "Redirect chains are not currently integrated",
                        "status": "planned",
                        "requires": "Redirect Resolution Engine (separate module)",
                        "impact": "Future enhancement for complete URL consolidation analysis"
                    }
                },
                "limitations": {
                    "non_crawled_variants": {
                        "description": "Cannot detect URL variants that are not internally linked or declared as canonical",
                        "requires": "Server log files or Google Search Console data",
                        "impact": "May miss externally-linked variants or orphaned pages"
                    },
                    "canonical_intent_confidence": {
                        "description": "Intent confidence is heuristic based on crawl data only",
                        "requires": "Google indexation data, impressions, and ranking signals for perfect accuracy",
                        "impact": "Directionally correct but not Google-perfect"
                    }
                },
                "data_sources": ["internal_crawl", "link_graph"],
                "recommended_supplements": ["google_search_console", "server_logs", "analytics"]
            }
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"✓ Results exported to {output_path}")
        
        # INTEGRATION: Generate page-to-cluster index
        self._generate_page_index(output_path)
        
        return output_data
    
    def _generate_page_index(self, cluster_output_path: Path):
        """INTEGRATION: Generate page-to-cluster mapping for SEO agent"""
        logger.info("Generating page-to-cluster index...")
        
        page_index = {}
        
        for cluster in self.clusters.values():
            for member in cluster.members:
                page_index[member.normalized_url] = {
                    "cluster_id": cluster.cluster_id,
                    "canonical_leader": cluster.canonical_leader,
                    "is_canonical": member.normalized_url == cluster.canonical_leader,
                    "issues": cluster.issues,
                    "severity": cluster.severity,
                    "fix_priority": cluster.fix_priority,
                    "recommended_action": cluster.recommended_action
                }
        
        # Save to same directory as cluster output
        index_path = cluster_output_path.parent / f"{cluster_output_path.stem}_page_index.json"
        with open(index_path, 'w', encoding='utf-8') as f:
            json.dump(page_index, f, indent=2, ensure_ascii=False)
        
        logger.info(f"✓ Page index exported to {index_path}")
    
    def calculate_severity(self):
        """Calculate severity and actionability (ENHANCED with cluster metrics)"""
        logger.info("Calculating severity and recommendations...")
        
        for cluster in self.clusters.values():
            severity = "low"
            seo_impact = []
            recommended_action = "No action needed"
            priority = 1
            
            # Calculate cluster metrics for severity refinement
            cluster_size = len(cluster.members)
            authority_loss_pct = int(cluster.authority.get('leakage', 0) * 100)
            seo_eligible_pages = sum(1 for m in cluster.members if m.is_indexable and m.status_code == 200)
            
            # Get example URLs for recommendations
            non_leader_members = [m for m in cluster.members if m.normalized_url != cluster.canonical_leader]
            example_url = non_leader_members[0].url if non_leader_members else ""
            
            # CRITICAL SEVERITY
            if "CANONICAL_TO_NON_INDEXABLE" in cluster.issues:
                severity = "critical"
                priority = 5
                seo_impact.append("indexing")
                recommended_action = (
                    f"CRITICAL: {cluster_size} pages point to non-indexable canonical. "
                    f"Update canonical tag on all pages to point to indexable URL. "
                    f"Example affected page: {example_url}"
                )
            
            elif "CANONICAL_TO_ERROR_PAGE" in cluster.issues:
                severity = "critical"
                priority = 5
                seo_impact.append("indexing")
                recommended_action = (
                    f"CRITICAL: {cluster_size} pages point to error page (non-200). "
                    f"Fix canonical tag to point to working URL. "
                    f"Example: {example_url}"
                )
            
            # HIGH SEVERITY
            elif cluster.chain_depth >= 2:
                severity = "high"
                priority = 4
                seo_impact.append("crawl_budget")
                chain_display = " → ".join(cluster.canonical_chain[:3])  # Show first 3 in chain
                recommended_action = (
                    f"Canonical chain detected (depth {cluster.chain_depth}): {chain_display}. "
                    f"Update all pages to point directly to final canonical: {cluster.canonical_leader}"
                )
            
            elif cluster.authority.get('leakage', 0) > 0.5:
                severity = "high"
                priority = 5  # Boosted to critical if > 50%
                seo_impact.append("ranking")
                recommended_action = (
                    f"HIGH AUTHORITY LEAKAGE: {authority_loss_pct}% of link equity is fragmented across {cluster_size} URLs. "
                    f"Implement 301 redirects from variant URLs to canonical: {cluster.canonical_leader}. "
                    f"Affected pages: {seo_eligible_pages} indexable"
                )
            
            elif "CANONICAL_TO_HOMEPAGE" in cluster.issues:
                severity = "high"
                priority = 4
                seo_impact.append("ranking")
                recommended_action = (
                    f"Remove homepage canonical from {cluster_size - 1} pages. "
                    f"These pages should be self-canonical or point to their proper canonical URL, not homepage. "
                    f"Example: {example_url}"
                )
            
            elif "WRONG_CANONICAL" in cluster.issues:
                severity = "high"
                priority = 4
                seo_impact.append("ranking")
                recommended_action = (
                    f"Canonical mismatch: Site declares '{cluster.declared_canonical}' but optimal is '{cluster.canonical_leader}'. "
                    f"Update canonical tags on {cluster_size} pages to point to: {cluster.canonical_leader}"
                )
            
            # MEDIUM SEVERITY
            elif "CANONICAL_CHAIN" in cluster.issues:
                severity = "medium"
                priority = 3
                seo_impact.append("crawl_budget")
                recommended_action = (
                    f"Simplify canonical chain (depth: {cluster.chain_depth}). "
                    f"Update intermediate pages to point directly to: {cluster.canonical_leader}"
                )
            
            elif "EXTERNAL_CANONICAL_TARGET" in cluster.issues:
                severity = "medium"
                priority = 3
                seo_impact.append("indexing")
                recommended_action = (
                    f"Canonical points to external domain. "
                    f"Verify this is intentional (e.g., syndicated content). "
                    f"If not, update to point to internal URL."
                )
            
            elif "CANONICAL_POINTS_TO_REDIRECT" in cluster.issues:
                severity = "medium"
                priority = 3
                seo_impact.append("crawl_budget")
                recommended_action = (
                    f"Canonical URL itself redirects. "
                    f"Update canonical to point to final destination URL. "
                    f"Canonical should be: {cluster.canonical_leader}"
                )
            
            elif "CANONICAL_FINAL_URL_MISMATCH" in cluster.issues:
                severity = "medium"
                priority = 3
                seo_impact.append("indexing")
                recommended_action = (
                    f"Canonical URL resolves to different final URL after redirects. "
                    f"Update canonical to match final destination or remove redirect chain."
                )
            
            elif cluster.authority.get('leakage', 0) > 0.3:
                severity = "medium"
                priority = 3
                seo_impact.append("ranking")
                recommended_action = (
                    f"Authority leakage: {authority_loss_pct}% of link equity fragmented. "
                    f"Consider 301 redirects or updating internal links to consolidate to: {cluster.canonical_leader}"
                )
            
            elif "TRAILING_SLASH_VARIANT" in cluster.issues or "PARAMETER_VARIANT" in cluster.issues:
                severity = "medium"
                priority = 3
                seo_impact.append("duplicate_content")
                variant_type = "trailing slash" if "TRAILING_SLASH_VARIANT" in cluster.issues else "parameter"
                recommended_action = (
                    f"URL variants detected ({variant_type}). "
                    f"Enforce consistent URL policy: either 301 redirect variants or use rel=canonical. "
                    f"Canonical should be: {cluster.canonical_leader}"
                )
            
            elif "INTERNAL_LINK_MISALIGNMENT" in cluster.issues:
                severity = "medium"
                priority = 3
                seo_impact.append("ranking")
                misaligned = cluster.internal_link_alignment.get('non_canonical_inlinks', 0)
                recommended_action = (
                    f"Internal link misalignment: {misaligned} internal links point to non-canonical URLs. "
                    f"Update internal links to point to canonical: {cluster.canonical_leader}"
                )
            
            # LOW SEVERITY
            elif "SOFT_DUPLICATE_CONTENT" in cluster.issues:
                severity = "low"
                priority = 2
                seo_impact.append("duplicate_content")
                dup_count = len(cluster.soft_duplicates)
                recommended_action = (
                    f"Soft duplicate content detected ({dup_count} similar pages). "
                    f"Review content similarity and consolidate or differentiate."
                )
            
            elif len(cluster.members) > 1:
                severity = "low"
                priority = 2
                seo_impact.append("optimization")
                recommended_action = (
                    f"Monitor cluster with {cluster_size} URLs. "
                    f"No immediate action required but watch for authority fragmentation."
                )
            
            # Severity boosters based on cluster metrics (FIXED: gate by SEO-eligible pages)
            if seo_eligible_pages > 10:
                priority = min(5, priority + 1)
                severity = "high" if severity == "medium" else severity
            if seo_eligible_pages > 5:
                priority = min(5, priority + 1)
            if cluster.link_leakage_ratio > 0.5:
                priority = min(5, priority + 1)
            if seo_eligible_pages > 5 and authority_loss_pct > 30:
                priority = min(5, priority + 1)
            
            cluster.severity = severity
            cluster.fix_priority = priority
            cluster.seo_impact = seo_impact
            cluster.recommended_action = recommended_action
        
        logger.info("✓ Severity and recommendations calculated")
    
    def analyze(self, output_path: Optional[str] = None) -> Dict:
        """Run complete canonical cluster analysis"""
        self.build_canonical_map()
        self.resolve_canonical_chains()
        self.build_clusters()
        self.select_cluster_leaders()
        self.analyze_canonical_alignment()
        self.calculate_authority()
        self.detect_issues()
        self.calculate_severity()
        
        if output_path:
            return self.export_results(output_path)
        
        return {
            "clusters": [asdict(c) for c in self.clusters.values()],
            "summary": self.get_summary()
        }


if __name__ == "__main__":
    import sys
    
    # Manual path input
    # Check if paths provided via command line
    if len(sys.argv) >= 3:
        pages_json = sys.argv[1]
        link_graph_json = sys.argv[2]
        redirect_map_json = sys.argv[3] if len(sys.argv) > 3 else None
        output_json = sys.argv[4] if len(sys.argv) > 4 else None
        
        if not output_json:
            input_path = Path(pages_json)
            output_json = str(input_path.parent / f"{input_path.stem}_canonical_clusters.json")
            print(f"✓ Output will be saved to: {output_json}")
    else:
        print("=" * 70)
        print("🧬 CANONICAL CLUSTER ANALYZER")
        print("=" * 70)
        print("\nEnter paths to your data files:")
        print()
        
        pages_json = input("Crawler pages JSON: ").strip()
        link_graph_json = input("Link graph JSON: ").strip()
        
        if not pages_json or not link_graph_json:
            print("❌ Error: Both paths required")
            sys.exit(1)
        
        # Ask for redirect map (optional)
        print("\nEnter path to redirect_map.json (optional, press Enter to skip):")
        print("Example: crawler_output/developer_mozilla_org_20251220_054821_pages_redirect_map.json")
        redirect_map_json = input("Redirect map path (optional): ").strip() or None
        
        if redirect_map_json and not Path(redirect_map_json).exists():
            print(f"⚠️  Warning: Redirect map file not found: {redirect_map_json}")
            print("   Continuing without redirect precedence...")
            redirect_map_json = None
        
        print("\nEnter output path (press Enter to auto-generate):")
        output_json = input("Output path (optional): ").strip()
        
        if not output_json:
            input_path = Path(pages_json)
            output_json = str(input_path.parent / f"{input_path.stem}_canonical_clusters.json")
            print(f"✓ Output will be saved to: {output_json}")
    
    print(f"\n🧬 Analyzing canonical clusters...")
    if redirect_map_json:
        print(f"   Using redirect map for precedence: {redirect_map_json}")
    analyzer = CanonicalClusterAnalyzer(pages_json, link_graph_json, redirect_map_json)
    results = analyzer.analyze(output_json)
    
    # Print summary
    print("\n" + "=" * 70)
    print("📊 CANONICAL CLUSTER SUMMARY")
    print("=" * 70)
    summary = results['summary']
    print(f"Total Clusters: {summary['total_clusters']}")
    print(f"  → Single-URL clusters: {summary['single_url_clusters']}")
    print(f"  → Multi-URL clusters: {summary['multi_url_clusters']}")
    print(f"⚠️  Clusters with Issues: {summary['clusters_with_issues']}")
    print(f"📉 Authority Leakage (>30%): {summary['authority_leakage_clusters']}")
    
    if summary.get('issue_breakdown'):
        print("\n🔍 Issue Breakdown:")
        for issue, count in summary['issue_breakdown'].items():
            print(f"  → {issue}: {count}")
    
    print("=" * 70)
