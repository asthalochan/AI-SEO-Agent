"""
Redirect Resolution Engine
Enterprise-grade redirect analysis and issue detection

Purpose:
    Analyze redirect chains, detect issues, and provide actionable recommendations
    for SEO optimization. Integrates with crawler, canonical analyzer, and link graph.

Key Features:
    - Redirect chain analysis
    - Loop detection
    - 7 comprehensive issue detection rules
    - Integration with existing SEO modules
    - Actionable recommendations

Author: SEO Analysis Suite
Version: 1.0.0
"""

import json
import logging
from typing import Dict, List, Set, Optional, Any
from dataclasses import dataclass, asdict, field
from pathlib import Path
from collections import defaultdict
from urllib.parse import urlparse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class RedirectRecord:
    """Represents a redirect chain for a single URL"""
    url: str
    initial_status: int
    redirect_chain: List[Dict[str, Any]] = field(default_factory=list)
    final_url: str = ""
    final_status: int = 0
    chain_length: int = 0
    has_loop: bool = False
    redirect_type: Dict[str, str] = field(default_factory=dict)  # Structured: protocol_change, www_change, path_change, status_type
    crawl_depth: int = 0
    source_depth: int = 0  # For variants: depth of source page that generated this variant
    is_from_variant_test: bool = False  # True if from variant_crawler, False if from crawler
    canonical_vs_redirect: str = "ok"  # NEW: ok | canonical_to_redirect | redirect_to_canonical
    internal_link_sources: List[str] = field(default_factory=list)  # NEW: URLs that link to this redirect


@dataclass
class RedirectIssue:
    """Represents a redirect-related SEO issue"""
    issue_id: str
    title: str
    severity: str  # critical, high, medium, low
    affected_url: str
    final_url: str = ""
    impact: str = ""
    recommendation: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


class RedirectResolver:
    """Analyzes redirect chains and detects SEO issues"""
    
    # Redirect status codes
    REDIRECT_STATUSES = {301, 302, 303, 307, 308}
    PERMANENT_REDIRECTS = {301, 308}
    TEMPORARY_REDIRECTS = {302, 303, 307}
    
    def __init__(self, pages_json_path: str, 
                 redirect_variants_json_path: Optional[str] = None,
                 link_graph_json_path: Optional[str] = None, 
                 canonical_clusters_json_path: Optional[str] = None):
        """
        Initialize redirect resolver
        
        Args:
            pages_json_path: Path to crawler pages JSON
            redirect_variants_json_path: Optional path to redirect_variants.json from variant_crawler
            link_graph_json_path: Optional path to link graph JSON
            canonical_clusters_json_path: Optional path to canonical clusters JSON
        """
        self.pages_json_path = Path(pages_json_path)
        self.redirect_variants_json_path = Path(redirect_variants_json_path) if redirect_variants_json_path else None
        self.link_graph_json_path = Path(link_graph_json_path) if link_graph_json_path else None
        self.canonical_clusters_json_path = Path(canonical_clusters_json_path) if canonical_clusters_json_path else None
        
        # Load data
        self.pages_data = self._load_json(self.pages_json_path)
        self.redirect_variants_data = self._load_json(self.redirect_variants_json_path) if self.redirect_variants_json_path else None
        self.link_graph_data = self._load_json(self.link_graph_json_path) if self.link_graph_json_path else None
        self.canonical_clusters_data = self._load_json(self.canonical_clusters_json_path) if self.canonical_clusters_json_path else None
        
        # Analysis results (FIXED: Separate crawl vs variant redirects)
        self.crawl_redirects: Dict[str, RedirectRecord] = {}  # What crawler experienced (diagnostic only)
        self.variant_redirects: Dict[str, RedirectRecord] = {}  # Authoritative redirect truth (SEO decisions)
        self.redirect_map: Dict[str, RedirectRecord] = {}  # Combined map for export
        self.issues: List[RedirectIssue] = []
        self.summary: Dict[str, Any] = {}
    
    def _load_json(self, path: Path) -> Any:
        """Load JSON file"""
        if not path or not path.exists():
            return None
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def build_redirect_map(self):
        """Build redirect maps (FIXED: Separate crawl vs variant)"""
        logger.info(f"Building redirect maps from {len(self.pages_data)} pages...")
        
        # LAYER 1: Crawl redirects (diagnostic only)
        for page in self.pages_data:
            url = page['normalized_url']
            redirect_chain = page.get('redirect_chain', [])
            final_url = page.get('final_url', url)
            final_status = page.get('final_status', page.get('status_code', 0))
            initial_status = page.get('status_code', 0)
            
            # Determine redirect type (structured)
            redirect_type = self._classify_redirect_type(redirect_chain)
            
            # Detect loops
            has_loop = self._detect_loop(redirect_chain)
            
            record = RedirectRecord(
                url=url,
                initial_status=initial_status,
                redirect_chain=redirect_chain,
                final_url=final_url,
                final_status=final_status,
                chain_length=len(redirect_chain),
                has_loop=has_loop,
                redirect_type=redirect_type,
                crawl_depth=page.get('crawl_depth', 0),
                source_depth=page.get('crawl_depth', 0),
                is_from_variant_test=False
            )
            
            self.crawl_redirects[url] = record
        
        logger.info(f"✓ Built crawl redirect map: {len(self.crawl_redirects)} URLs")
        
        # LAYER 2: Variant redirects (authoritative truth)
        if self.redirect_variants_data:
            self._build_variant_redirects()
        
        # Merge for export (variant redirects override crawl redirects)
        self._merge_redirect_layers()
    
    def _build_variant_redirects(self):
        """Build variant redirect map (AUTHORITATIVE TRUTH)"""
        logger.info("Building variant redirect map (authoritative)...")
        
        variant_tests = self.redirect_variants_data.get('tests', [])
        variant_count = 0
        
        for test in variant_tests:
            url = test.get('tested_variant')
            redirect_chain = test.get('redirect_chain', [])
            final_url = test.get('final_url', url)
            final_status = test.get('final_status', 0)
            initial_status = test.get('initial_status', 0)
            source_url = test.get('source_url', '')  # URL that generated this variant
            
            # Get source page depth
            source_depth = 0
            if source_url:
                source_page = next((p for p in self.pages_data if p['normalized_url'] == source_url), None)
                if source_page:
                    source_depth = source_page.get('crawl_depth', 0)
            
            # Determine redirect type (structured)
            redirect_type = self._classify_redirect_type(redirect_chain)
            
            # Detect loops
            has_loop = self._detect_loop(redirect_chain)
            
            record = RedirectRecord(
                url=url,
                initial_status=initial_status,
                redirect_chain=redirect_chain,
                final_url=final_url,
                final_status=final_status,
                chain_length=len(redirect_chain),
                has_loop=has_loop,
                redirect_type=redirect_type,
                crawl_depth=0,  # Variants aren't crawled
                source_depth=source_depth,
                is_from_variant_test=True
            )
            
            self.variant_redirects[url] = record
            variant_count += 1
        
        logger.info(f"✓ Built variant redirect map: {variant_count} authoritative redirects")
    
    def _merge_redirect_layers(self):
        """Merge crawl and variant redirects (variant takes precedence)"""
        logger.info("Merging redirect layers...")
        
        # Start with crawl redirects
        self.redirect_map = dict(self.crawl_redirects)
        
        # Override with variant redirects (authoritative)
        self.redirect_map.update(self.variant_redirects)
        
        logger.info(f"✓ Final redirect map: {len(self.redirect_map)} URLs ({len(self.variant_redirects)} from variants)")
    
    def _classify_redirect_type(self, redirect_chain: List[Dict[str, Any]]) -> Dict[str, str]:
        """Classify redirect type based on chain analysis (FIXED: Returns structured dict)"""
        if not redirect_chain or len(redirect_chain) == 0:
            return {}
        
        # Get first and last URLs in chain
        first_url = redirect_chain[0].get('url', '')
        last_url = redirect_chain[-1].get('url', '') if len(redirect_chain) > 1 else first_url
        
        # Parse URLs
        parsed_first = urlparse(first_url)
        parsed_last = urlparse(last_url)
        
        redirect_type = {}
        
        # Check for protocol change
        if parsed_first.scheme != parsed_last.scheme:
            if parsed_last.scheme == 'https':
                redirect_type['protocol_change'] = 'http_to_https'
            else:
                redirect_type['protocol_change'] = 'https_to_http'
        
        # Check for WWW consolidation
        first_has_www = 'www.' in parsed_first.netloc
        last_has_www = 'www.' in parsed_last.netloc
        if first_has_www != last_has_www:
            if last_has_www:
                redirect_type['www_change'] = 'non_www_to_www'
            else:
                redirect_type['www_change'] = 'www_to_non_www'
        
        # Check for trailing slash
        first_path_no_slash = parsed_first.path.rstrip('/')
        last_path_no_slash = parsed_last.path.rstrip('/')
        if first_path_no_slash == last_path_no_slash and parsed_first.path != parsed_last.path:
            redirect_type['path_change'] = 'trailing_slash'
        
        # Check for locale redirect
        elif '/en-US/' in parsed_last.path and '/en-US/' not in parsed_first.path:
            redirect_type['path_change'] = 'locale_redirect'
        
        # Check for path migration (path changed but not just trailing slash/locale)
        elif parsed_first.path != parsed_last.path:
            redirect_type['path_change'] = 'path_migration'
        
        # Determine if permanent or temporary based on status codes
        statuses = {hop.get('status', 0) for hop in redirect_chain}
        has_permanent = bool(statuses & self.PERMANENT_REDIRECTS)
        has_temporary = bool(statuses & self.TEMPORARY_REDIRECTS)
        
        if has_permanent and has_temporary:
            redirect_type['status_type'] = 'mixed_status'
        elif has_permanent:
            redirect_type['status_type'] = 'permanent'
        elif has_temporary:
            redirect_type['status_type'] = 'temporary'
        
        return redirect_type
    
    def _detect_loop(self, redirect_chain: List[Dict[str, Any]]) -> bool:
        """Detect if redirect chain contains a loop"""
        if not redirect_chain:
            return False
        
        seen_urls = set()
        for hop in redirect_chain:
            url = hop.get('url', '')
            if url in seen_urls:
                return True
            seen_urls.add(url)
        
        return False
    
    def _normalize_url(self, url: str) -> str:
        """Normalize URL for consistent comparison (HELPER for canonical checks)"""
        if not url:
            return url
        
        parsed = urlparse(url)
        
        # Normalize scheme
        scheme = parsed.scheme.lower() if parsed.scheme else 'https'
        
        # Normalize netloc
        netloc = parsed.netloc.lower()
        
        # Normalize path (remove trailing slash for non-root paths)
        path = parsed.path if parsed.path else '/'
        if path != '/' and path.endswith('/'):
            path = path.rstrip('/')
        
        # Rebuild URL
        normalized = f"{scheme}://{netloc}{path}"
        if parsed.query:
            normalized += f"?{parsed.query}"
        if parsed.fragment:
            normalized += f"#{parsed.fragment}"
        
        return normalized
    
    def _resolve_url_via_variants(self, url: str) -> str:
        """
        Resolve URL through variant redirects (authoritative truth)
        Falls back to crawl redirects if not found in variants
        
        Args:
            url: URL to resolve
            
        Returns:
            Final URL after following redirects
        """
        if not url:
            return url
        
        # Normalize first
        normalized = self._normalize_url(url)
        
        # Check variant redirects first (authoritative)
        if normalized in self.variant_redirects:
            record = self.variant_redirects[normalized]
            return record.final_url if record.final_url else normalized
        
        # Fallback to crawl redirects
        if normalized in self.crawl_redirects:
            record = self.crawl_redirects[normalized]
            return record.final_url if record.final_url else normalized
        
        # No redirect found
        return normalized
    
    def detect_issues(self):
        """Detect all redirect-related issues"""
        logger.info("Detecting redirect issues...")
        
        self._detect_redirect_chains()
        self._detect_redirect_loops()
        self._detect_canonical_redirect_conflicts()
        self._detect_redirecting_canonicals()
        self._detect_internal_links_to_redirects()
        self._detect_mixed_redirect_types()
        self._detect_https_www_consolidation()
        
        logger.info(f"✓ Detected {len(self.issues)} redirect issues")
    
    def _detect_redirect_chains(self):
        """RULE 1: Detect redirect chains (>1 hop)"""
        for url, record in self.redirect_map.items():
            if record.chain_length > 1:
                severity = "medium" if record.chain_length == 2 else "high"
                
                issue = RedirectIssue(
                    issue_id=f"REDIRECT_CHAIN_{len(self.issues)}",
                    title="Redirect Chain Detected",
                    severity=severity,
                    affected_url=url,
                    final_url=record.final_url,
                    impact=f"Redirect chain with {record.chain_length} hops dilutes link equity and slows page load.",
                    recommendation=f"Simplify to single redirect: {url} → {record.final_url}",
                    metadata={"chain_length": record.chain_length, "chain": record.redirect_chain}
                )
                self.issues.append(issue)
    
    def _detect_redirect_loops(self):
        """RULE 2: Detect redirect loops (CRITICAL)"""
        for url, record in self.redirect_map.items():
            if record.has_loop:
                issue = RedirectIssue(
                    issue_id=f"REDIRECT_LOOP_{len(self.issues)}",
                    title="Redirect Loop Detected",
                    severity="critical",
                    affected_url=url,
                    final_url="",
                    impact="Infinite redirect loop prevents page access and causes crawl errors.",
                    recommendation=f"Fix redirect loop immediately. Remove circular redirects in chain.",
                    metadata={"chain": record.redirect_chain}
                )
                self.issues.append(issue)
    
    def _detect_canonical_redirect_conflicts(self):
        """RULE 3: Detect canonical → redirect conflicts (ENHANCED: Track canonical_vs_redirect)"""
        if not self.canonical_clusters_data:
            return
        
        for cluster in self.canonical_clusters_data.get('clusters', []):
            canonical_leader = cluster.get('canonical_leader', '')
            
            # Resolve canonical through variant redirects first (authoritative)
            canonical_final = self._resolve_url_via_variants(canonical_leader)
            
            # NEW: Mark canonical_vs_redirect status in redirect records
            if canonical_final != canonical_leader:
                # Canonical points to redirecting URL
                if canonical_leader in self.redirect_map:
                    self.redirect_map[canonical_leader].canonical_vs_redirect = "canonical_to_redirect"
                
                issue = RedirectIssue(
                    issue_id=f"CANONICAL_REDIRECT_CONFLICT_{len(self.issues)}",
                    title="Canonical URL Redirects to Different URL",
                    severity="high",
                    affected_url=canonical_leader,
                    final_url=canonical_final,
                    impact="Google may ignore canonical tag when canonical URL redirects.",
                    recommendation=f"Update canonical to final URL: {canonical_final}",
                    metadata={"cluster_id": cluster.get('cluster_id'), "canonical_vs_redirect": "canonical_to_redirect"}
                )
                self.issues.append(issue)
            
            # NEW: Check if any members redirect to canonical (reverse case)
            for member in cluster.get('members', []):
                member_url = member.get('url', '')
                if member_url in self.redirect_map:
                    record = self.redirect_map[member_url]
                    if record.chain_length > 0 and record.final_url == canonical_leader:
                        record.canonical_vs_redirect = "redirect_to_canonical"
    
    def _detect_redirecting_canonicals(self):
        """RULE 4: Detect redirecting canonicals (FIXED: Variant-aware with normalization)"""
        if not self.canonical_clusters_data:
            return
        
        for cluster in self.canonical_clusters_data.get('clusters', []):
            for member in cluster.get('members', []):
                declared_canonical = member.get('declared_canonical', '')
                
                if declared_canonical:
                    # FIXED: Normalize and resolve through variants
                    canonical_normalized = self._normalize_url(declared_canonical)
                    canonical_final = self._resolve_url_via_variants(canonical_normalized)
                    
                    if canonical_final != canonical_normalized:
                        issue = RedirectIssue(
                            issue_id=f"REDIRECTING_CANONICAL_{len(self.issues)}",
                            title="Canonical Tag Points to Redirecting URL",
                            severity="high",
                            affected_url=member.get('normalized_url', ''),
                            final_url=canonical_final,
                            impact="Canonical tag points to URL that redirects, causing SEO confusion.",
                            recommendation=f"Update canonical to non-redirecting URL: {canonical_final}",
                            metadata={"declared_canonical": declared_canonical, "canonical_normalized": canonical_normalized}
                        )
                        self.issues.append(issue)
                        break  # One issue per cluster
    
    def _detect_internal_links_to_redirects(self):
        """RULE 5: Detect internal links pointing to redirects (ENHANCED: Track sources)"""
        if not self.link_graph_data:
            return
        
        # NEW: Build internal link sources for each redirect
        link_graph_pages = self.link_graph_data.get('pages', [])
        
        for page_data in link_graph_pages:
            source_url = page_data.get('url', '')
            outlinks = page_data.get('resolved_outlink_urls', [])
            
            # Check each outlink to see if it's a redirect
            for target_url in outlinks:
                if target_url in self.redirect_map:
                    record = self.redirect_map[target_url]
                    if record.chain_length > 0:
                        # This is a redirect - track the source
                        if source_url not in record.internal_link_sources:
                            record.internal_link_sources.append(source_url)
        
        # Generate issues for redirects with internal links
        link_graph_nodes = self.link_graph_data.get('nodes', [])
        
        for node in link_graph_nodes:
            url = node.get('normalized_url', '')
            links_to_redirects = node.get('links_to_redirects', 0)
            
            if links_to_redirects > 0:
                # Get the redirect record to include sources
                redirect_record = self.redirect_map.get(url)
                sources = redirect_record.internal_link_sources if redirect_record else []
                
                issue = RedirectIssue(
                    issue_id=f"INTERNAL_LINKS_TO_REDIRECTS_{len(self.issues)}",
                    title="Internal Links Point to Redirecting URLs",
                    severity="high",
                    affected_url=url,
                    final_url="",
                    impact=f"{links_to_redirects} internal links point to redirecting URLs, diluting link equity.",
                    recommendation=f"Update {links_to_redirects} internal links to point directly to final URLs.",
                    metadata={
                        "links_to_redirects": links_to_redirects,
                        "internal_link_sources": sources[:10]  # Limit to first 10 for readability
                    }
                )
                self.issues.append(issue)
    
    def _detect_mixed_redirect_types(self):
        """RULE 6: Detect mixed redirect types (FIXED: Check structured redirect_type)"""
        for url, record in self.redirect_map.items():
            # FIXED: Check for 'mixed_status' in structured redirect_type dict
            if record.redirect_type.get('status_type') == 'mixed_status':
                issue = RedirectIssue(
                    issue_id=f"MIXED_REDIRECT_TYPES_{len(self.issues)}",
                    title="Mixed Redirect Types in Chain",
                    severity="medium",
                    affected_url=url,
                    final_url=record.final_url,
                    impact="Mixed 301/302 redirects signal instability and confuse search engines.",
                    recommendation="Use consistent redirect type (prefer 301 for permanent moves).",
                    metadata={"chain": record.redirect_chain, "redirect_type": record.redirect_type}
                )
                self.issues.append(issue)
    
    def _detect_https_www_consolidation(self):
        """RULE 7: Detect HTTPS/WWW consolidation issues"""
        for url, record in self.redirect_map.items():
            if record.chain_length == 0:
                continue
            
            parsed_initial = urlparse(url)
            parsed_final = urlparse(record.final_url)
            
            # Check for http → https
            is_https_redirect = parsed_initial.scheme == 'http' and parsed_final.scheme == 'https'
            
            # Check for www consolidation
            is_www_redirect = (
                ('www.' not in parsed_initial.netloc and 'www.' in parsed_final.netloc) or
                ('www.' in parsed_initial.netloc and 'www.' not in parsed_final.netloc)
            )
            
            if is_https_redirect or is_www_redirect:
                severity = "low" if record.chain_length == 1 and record.redirect_type == "permanent" else "high"
                redirect_reason = []
                if is_https_redirect:
                    redirect_reason.append("HTTP → HTTPS")
                if is_www_redirect:
                    redirect_reason.append("WWW consolidation")
                
                issue = RedirectIssue(
                    issue_id=f"HTTPS_WWW_CONSOLIDATION_{len(self.issues)}",
                    title=f"{' + '.join(redirect_reason)} Redirect",
                    severity=severity,
                    affected_url=url,
                    final_url=record.final_url,
                    impact="Protocol/subdomain consolidation redirect detected.",
                    recommendation="Ensure single-hop permanent (301) redirect for best SEO." if severity == "high" else "Redirect is properly configured.",
                    metadata={"redirect_reason": redirect_reason, "chain_length": record.chain_length}
                )
                self.issues.append(issue)
    
    def generate_summary(self):
        """Generate summary statistics (ENHANCED: Add redirect efficiency score)"""
        logger.info("Generating redirect summary...")
        
        total_urls = len(self.redirect_map)
        redirecting_urls = sum(1 for r in self.redirect_map.values() if r.chain_length > 0)
        chains = sum(1 for r in self.redirect_map.values() if r.chain_length > 1)
        loops = sum(1 for r in self.redirect_map.values() if r.has_loop)
        
        # Count internal links to redirects from link graph
        internal_links_to_redirects = 0
        if self.link_graph_data:
            for node in self.link_graph_data.get('nodes', []):
                internal_links_to_redirects += node.get('links_to_redirects', 0)
        
        # Count canonical conflicts by type
        canonical_conflicts = sum(1 for issue in self.issues if 'CANONICAL' in issue.issue_id)
        canonical_to_redirect = sum(1 for r in self.redirect_map.values() if r.canonical_vs_redirect == "canonical_to_redirect")
        redirect_to_canonical = sum(1 for r in self.redirect_map.values() if r.canonical_vs_redirect == "redirect_to_canonical")
        
        # NEW: Calculate redirect efficiency score
        redirect_efficiency_score = round(1 - (redirecting_urls / total_urls), 3) if total_urls > 0 else 1.0
        
        # Group issues by severity
        issues_by_severity = defaultdict(int)
        for issue in self.issues:
            issues_by_severity[issue.severity] += 1
        
        self.summary = {
            "total_urls": total_urls,
            "redirecting_urls": redirecting_urls,
            "redirect_efficiency_score": redirect_efficiency_score,  # NEW
            "chains": chains,
            "loops": loops,
            "internal_links_to_redirects": internal_links_to_redirects,
            "canonical_conflicts": canonical_conflicts,
            "canonical_vs_redirect_breakdown": {  # NEW: Detailed breakdown
                "ok": total_urls - canonical_to_redirect - redirect_to_canonical,
                "canonical_to_redirect": canonical_to_redirect,
                "redirect_to_canonical": redirect_to_canonical
            },
            "total_issues": len(self.issues),
            "issues_by_severity": dict(issues_by_severity)
        }
        
        logger.info(f"✓ Summary generated: {redirecting_urls} redirecting URLs, {len(self.issues)} issues, efficiency: {redirect_efficiency_score}")
    
    def export_results(self, output_dir: str = "crawler_output"):
        """Export all results to JSON files"""
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True)
        
        # Generate base filename from pages JSON
        base_name = self.pages_json_path.stem
        
        # Export redirect map
        redirect_map_path = output_path / f"{base_name}_redirect_map.json"
        redirect_map_export = {
            url: asdict(record) for url, record in self.redirect_map.items()
        }
        with open(redirect_map_path, 'w', encoding='utf-8') as f:
            json.dump(redirect_map_export, f, indent=2, ensure_ascii=False)
        logger.info(f"✓ Redirect map exported to {redirect_map_path}")
        
        # Export issues grouped by severity
        redirect_issues_path = output_path / f"{base_name}_redirect_issues.json"
        issues_grouped = {
            "critical": [asdict(i) for i in self.issues if i.severity == "critical"],
            "high": [asdict(i) for i in self.issues if i.severity == "high"],
            "medium": [asdict(i) for i in self.issues if i.severity == "medium"],
            "low": [asdict(i) for i in self.issues if i.severity == "low"]
        }
        with open(redirect_issues_path, 'w', encoding='utf-8') as f:
            json.dump(issues_grouped, f, indent=2, ensure_ascii=False)
        logger.info(f"✓ Redirect issues exported to {redirect_issues_path}")
        
        # Export summary
        redirect_summary_path = output_path / f"{base_name}_redirect_summary.json"
        with open(redirect_summary_path, 'w', encoding='utf-8') as f:
            json.dump(self.summary, f, indent=2, ensure_ascii=False)
        logger.info(f"✓ Redirect summary exported to {redirect_summary_path}")
        
        return {
            "redirect_map": str(redirect_map_path),
            "redirect_issues": str(redirect_issues_path),
            "redirect_summary": str(redirect_summary_path)
        }
    
    def analyze(self, output_dir: str = "crawler_output") -> Dict[str, Any]:
        """Run complete redirect analysis"""
        logger.info("🔄 Starting redirect resolution analysis...")
        
        self.build_redirect_map()
        self.detect_issues()
        self.generate_summary()
        output_paths = self.export_results(output_dir)
        
        logger.info("✅ Redirect analysis complete!")
        
        return {
            "summary": self.summary,
            "output_files": output_paths
        }


def analyze_redirects(pages_json_path: str, 
                     redirect_variants_json_path: Optional[str] = None,
                     link_graph_json_path: Optional[str] = None,
                     canonical_clusters_json_path: Optional[str] = None,
                     output_dir: str = "crawler_output") -> Dict[str, Any]:
    """
    Convenience function to analyze redirects
    
    Args:
        pages_json_path: Path to crawler pages JSON
        redirect_variants_json_path: Optional path to redirect_variants.json from variant_crawler
        link_graph_json_path: Optional path to link graph JSON
        canonical_clusters_json_path: Optional path to canonical clusters JSON
        output_dir: Output directory for results
        
    Returns:
        Analysis results
    """
    resolver = RedirectResolver(pages_json_path, redirect_variants_json_path, link_graph_json_path, canonical_clusters_json_path)
    return resolver.analyze(output_dir)


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("=" * 70)
        print("🔄 REDIRECT RESOLUTION ENGINE")
        print("=" * 70)
        print()
        print("Enter paths to your data files:")
        print()
        
        pages_json = input("Crawler pages JSON: ").strip()
        redirect_variants_json = input("Redirect variants JSON (optional, press Enter to skip): ").strip() or None
        link_graph_json = input("Link graph JSON (optional, press Enter to skip): ").strip() or None
        canonical_clusters_json = input("Canonical clusters JSON (optional, press Enter to skip): ").strip() or None
        
        print()
        print("Enter output directory (press Enter for 'crawler_output'):")
        output_dir = input("Output directory (optional): ").strip() or "crawler_output"
        
        print()
        print(f"✓ Output will be saved to: {output_dir}")
        print()
    else:
        pages_json = sys.argv[1]
        redirect_variants_json = sys.argv[2] if len(sys.argv) > 2 else None
        link_graph_json = sys.argv[3] if len(sys.argv) > 3 else None
        canonical_clusters_json = sys.argv[4] if len(sys.argv) > 4 else None
        output_dir = sys.argv[5] if len(sys.argv) > 5 else "crawler_output"
    
    results = analyze_redirects(pages_json, redirect_variants_json, link_graph_json, canonical_clusters_json, output_dir)
    
    print()
    print("=" * 70)
    print("REDIRECT ANALYSIS SUMMARY")
    print("=" * 70)
    for key, value in results['summary'].items():
        print(f"{key}: {value}")
