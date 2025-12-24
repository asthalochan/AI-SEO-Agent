"""
Variant Redirect Crawler
Post-crawl redirect discovery through URL variant testing

Purpose:
    Test URL variants (http/https, www/non-www, trailing slash) to discover
    redirects that weren't captured during initial crawl. This is a verification
    phase that mirrors Google's redirect evaluation process.

Architecture:
    Crawler → pages.json
    → Variant Crawler → redirect_variants.json
    → Redirect Resolver → redirect_map.json

Key Features:
    - Tests variants without modifying core crawler
    - Discovers protocol, subdomain, and path redirects
    - Tracks complete redirect chains
    - Safe, isolated, low-risk implementation

Author: SEO Analysis Suite
Version: 1.0.0
"""

import json
import logging
import time
from typing import Dict, List, Set, Optional, Any
from dataclasses import dataclass, asdict, field
from pathlib import Path
from urllib.parse import urlparse, urljoin
import requests

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class VariantTest:
    """Represents a redirect test for a URL variant"""
    tested_variant: str
    canonical_page: str  # The original crawled URL
    initial_status: int = 0
    redirect_chain: List[Dict[str, Any]] = field(default_factory=list)
    final_url: str = ""
    final_status: int = 0
    redirect_type: str = "none"
    test_timestamp: str = ""


class VariantRedirectCrawler:
    """Tests URL variants to discover redirects"""
    
    # Redirect status codes
    REDIRECT_STATUSES = {301, 302, 303, 307, 308}
    
    def __init__(self, pages_json_path: str, user_agent: str = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"):
        """
        Initialize variant crawler
        
        Args:
            pages_json_path: Path to crawler pages JSON
            user_agent: User agent for HTTP requests
        """
        self.pages_json_path = Path(pages_json_path)
        self.user_agent = user_agent
        
        # Load pages
        self.pages_data = self._load_json(self.pages_json_path)
        
        # Results
        self.variant_tests: List[VariantTest] = []
        self.tested_urls: Set[str] = set()
    
    def _load_json(self, path: Path) -> Any:
        """Load JSON file"""
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def _generate_url_variants(self, url: str) -> List[str]:
        """Generate URL variants to test for redirects"""
        variants = []
        parsed = urlparse(url)
        
        # HTTP/HTTPS variants
        if parsed.scheme == 'https':
            http_variant = url.replace('https://', 'http://')
            variants.append(http_variant)
        elif parsed.scheme == 'http':
            https_variant = url.replace('http://', 'https://')
            variants.append(https_variant)
        
        # WWW variants
        if 'www.' in parsed.netloc:
            non_www = url.replace('www.', '')
            variants.append(non_www)
        else:
            # Add www variant
            www_variant = url.replace('://', '://www.')
            variants.append(www_variant)
        
        # Trailing slash variants
        if parsed.path.endswith('/') and parsed.path != '/':
            no_slash = url.rstrip('/')
            variants.append(no_slash)
        elif not parsed.path.endswith('/'):
            with_slash = url + '/'
            variants.append(with_slash)
        
        # Locale variants (for root URLs)
        if parsed.path in ['/', '']:
            # Test common locale patterns
            base_url = f"{parsed.scheme}://{parsed.netloc}"
            variants.append(f"{base_url}/en-US/")
            variants.append(f"{base_url}/en/")
        
        # Remove duplicates and the original URL
        unique_variants = list(set(variants))
        if url in unique_variants:
            unique_variants.remove(url)
        
        return unique_variants
    
    def _test_redirect(self, url: str, max_redirects: int = 10) -> tuple:
        """
        Test a URL for redirects
        
        Returns:
            (redirect_chain, final_url, final_status)
        """
        redirect_chain = []
        current_url = url
        
        try:
            for hop in range(max_redirects):
                # Make HEAD request (faster than GET)
                try:
                    response = requests.head(
                        current_url,
                        allow_redirects=False,
                        timeout=10,
                        headers={'User-Agent': self.user_agent}
                    )
                except requests.exceptions.RequestException:
                    # Fallback to GET if HEAD fails
                    response = requests.get(
                        current_url,
                        allow_redirects=False,
                        timeout=10,
                        headers={'User-Agent': self.user_agent}
                    )
                
                status = response.status_code
                
                # Check if this is a redirect
                if status in self.REDIRECT_STATUSES:
                    # Record this hop
                    redirect_chain.append({
                        "url": current_url,
                        "status": status
                    })
                    
                    # Get redirect location
                    location = response.headers.get('Location')
                    if location:
                        # Handle relative redirects
                        next_url = urljoin(current_url, location)
                        current_url = next_url
                        continue
                    else:
                        # No location header, stop
                        break
                else:
                    # Not a redirect, this is the final page
                    return redirect_chain, current_url, status
            
            # Max redirects reached
            return redirect_chain, current_url, 0
            
        except Exception as e:
            logger.warning(f"Error testing {url}: {e}")
            return [], "", 0
    
    def _classify_redirect_type(self, original_url: str, final_url: str) -> str:
        """Classify redirect type"""
        if not final_url:
            return "none"
        
        parsed_orig = urlparse(original_url)
        parsed_final = urlparse(final_url)
        
        types = []
        
        # Protocol change
        if parsed_orig.scheme != parsed_final.scheme:
            if parsed_final.scheme == 'https':
                types.append('http_to_https')
            else:
                types.append('https_to_http')
        
        # WWW consolidation
        if 'www.' in parsed_orig.netloc and 'www.' not in parsed_final.netloc:
            types.append('www_to_non_www')
        elif 'www.' not in parsed_orig.netloc and 'www.' in parsed_final.netloc:
            types.append('non_www_to_www')
        
        # Trailing slash
        if parsed_orig.path.rstrip('/') == parsed_final.path.rstrip('/') and parsed_orig.path != parsed_final.path:
            types.append('trailing_slash')
        
        # Locale redirect
        if '/en-US/' in parsed_final.path and '/en-US/' not in parsed_orig.path:
            types.append('locale_redirect')
        
        return ','.join(types) if types else 'unknown'
    
    def test_variants(self):
        """Test variants for all crawled pages"""
        logger.info(f"Testing variants for {len(self.pages_data)} pages...")
        
        tested_count = 0
        redirect_count = 0
        
        for page in self.pages_data:
            canonical_url = page.get('normalized_url', page.get('url'))
            
            # Generate variants
            variants = self._generate_url_variants(canonical_url)
            
            for variant in variants:
                # Skip if already tested
                if variant in self.tested_urls:
                    continue
                
                self.tested_urls.add(variant)
                tested_count += 1
                
                # Test redirect
                redirect_chain, final_url, final_status = self._test_redirect(variant)
                
                # Classify redirect type
                redirect_type = self._classify_redirect_type(variant, final_url)
                
                # Create test record
                test = VariantTest(
                    tested_variant=variant,
                    canonical_page=canonical_url,
                    initial_status=redirect_chain[0]['status'] if redirect_chain else final_status,
                    redirect_chain=redirect_chain,
                    final_url=final_url or variant,
                    final_status=final_status,
                    redirect_type=redirect_type,
                    test_timestamp=time.strftime('%Y-%m-%d %H:%M:%S')
                )
                
                self.variant_tests.append(test)
                
                if redirect_chain:
                    redirect_count += 1
                    logger.info(f"✓ Redirect found: {variant} → {final_url} ({redirect_type})")
                
                # Rate limiting
                time.sleep(0.5)
        
        logger.info(f"✓ Tested {tested_count} variants, found {redirect_count} redirects")
    
    def export_results(self, output_dir: str = "crawler_output"):
        """Export variant test results"""
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True)
        
        # Generate filename
        base_name = self.pages_json_path.stem
        output_file = output_path / f"{base_name}_redirect_variants.json"
        
        # Export
        results = {
            "total_variants_tested": len(self.variant_tests),
            "redirects_found": sum(1 for t in self.variant_tests if t.redirect_chain),
            "tests": [asdict(test) for test in self.variant_tests]
        }
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        logger.info(f"✓ Variant tests exported to {output_file}")
        
        return str(output_file)
    
    def analyze(self, output_dir: str = "crawler_output") -> Dict[str, Any]:
        """Run complete variant analysis"""
        logger.info("🔄 Starting variant redirect crawler...")
        
        self.test_variants()
        output_file = self.export_results(output_dir)
        
        logger.info("✅ Variant redirect crawler complete!")
        
        return {
            "total_variants_tested": len(self.variant_tests),
            "redirects_found": sum(1 for t in self.variant_tests if t.redirect_chain),
            "output_file": output_file
        }


def test_variants(pages_json_path: str, output_dir: str = "crawler_output") -> Dict[str, Any]:
    """
    Convenience function to test URL variants
    
    Args:
        pages_json_path: Path to crawler pages JSON
        output_dir: Output directory for results
        
    Returns:
        Analysis results
    """
    crawler = VariantRedirectCrawler(pages_json_path)
    return crawler.analyze(output_dir)


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("=" * 70)
        print("🔄 VARIANT REDIRECT CRAWLER")
        print("=" * 70)
        print()
        print("Enter path to crawler pages JSON:")
        print()
        
        pages_json = input("Crawler pages JSON: ").strip()
        
        print()
        print("Enter output directory (press Enter for 'crawler_output'):")
        output_dir = input("Output directory (optional): ").strip() or "crawler_output"
        
        print()
        print(f"✓ Output will be saved to: {output_dir}")
        print()
    else:
        pages_json = sys.argv[1]
        output_dir = sys.argv[2] if len(sys.argv) > 2 else "crawler_output"
    
    results = test_variants(pages_json, output_dir)
    
    print()
    print("=" * 70)
    print("VARIANT CRAWLER SUMMARY")
    print("=" * 70)
    print(f"Total variants tested: {results['total_variants_tested']}")
    print(f"Redirects found: {results['redirects_found']}")
    print(f"Output file: {results['output_file']}")
