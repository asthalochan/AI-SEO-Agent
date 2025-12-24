"""
Enterprise-Grade Website Crawler v2.0
Production-ready SEO crawler with intelligent page classification
"""

import json
import re
import time
import hashlib
from collections import deque
from urllib.parse import urlparse, urljoin, parse_qs, urlunparse
from urllib import robotparser
from typing import Dict, List, Set, Optional, Any, Tuple
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from enum import Enum
import logging

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
from bs4 import BeautifulSoup

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class PageType(Enum):
    """Page type classification with specialized types"""
    CONTENT = "content"
    AUTH = "auth"
    LEGAL = "legal"
    ERROR = "error"
    UTILITY = "utility"
    DOCS_INDEX = "docs_index"  # Documentation index/navigation
    API_REFERENCE = "api_reference"  # API documentation
    GLOSSARY = "glossary"  # Glossary/definitions


@dataclass
class PageData:
    """Enhanced structured page data model with SEO intelligence"""
    # Basic Info (no defaults)
    url: str
    normalized_url: str
    domain: str
    status_code: int
    is_homepage: bool
    crawl_depth: int
    
    # SEO Metadata (no defaults for required fields)
    title: Optional[str]
    meta_description: Optional[str]
    h1: Optional[str]
    h2: List[str]
    h3: List[str]
    h1_count: int  # NEW: Heading counts for Content Quality Analyzer
    h2_count: int  # NEW
    h3_count: int  # NEW
    
    # Content Analysis (no defaults)
    content: str
    main_content: str
    word_count_raw: int
    word_count_main: int
    boilerplate_word_count: int
    link_density: float
    thin_content_exception: bool
    
    # Link Intelligence (no defaults)
    internal_links: List[str]
    internal_links_filtered: List[str]
    external_links: List[str]
    
    # Technical SEO (no defaults)
    canonical_url: str
    canonical_target: Optional[str]
    canonical_non_self: bool
    canonical_type: str
    canonical_intentional: bool
    protocol_mismatch: bool
    url_has_params: bool
    meta_robots: Optional[str]
    hreflang: List[str]
    pagination_rel: Optional[str]
    pagination_cluster_id: Optional[str]
    noindex: bool
    nofollow: bool
    blocked_by_robots: bool
    
    # Page Classification (no defaults)
    page_type: str
    indexable: bool
    indexability_reason: Optional[str]
    seo_eligible: bool
    
    # Metadata (no defaults)
    crawled_at: str
    url_hash: str
    
    # Fields with defaults (MUST come last)
    original_url: str = ""
    discovered_from: str = ""
    redirect_to: Optional[str] = None
    redirect_chain: List[Dict[str, Any]] = field(default_factory=list)
    final_url: Optional[str] = None
    final_status: Optional[int] = None
    
    def to_dict(self) -> Dict:
        return asdict(self)


class URLNormalizer:
    """Enhanced URL normalization with strict deduplication"""
    
    TRACKING_PARAMS = {
        'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content',
        'fbclid', 'gclid', 'ref', 'source', 'campaign', 'mc_cid', 'mc_eid'
    }
    
    SKIP_PARAMS = {
        'page', 'p', 'offset', 'limit', 'sort', 'order', 'filter'
    }
    
    @staticmethod
    def normalize(url: str, base_domain: str = None, remove_query: bool = False) -> Optional[str]:
        """
        Normalize URL following industry-standard SEO practices
        
        Rules (applied in order):
        1. Lowercase scheme + hostname
        2. Remove default ports (:80, :443)
        3. Remove fragment (#section)
        4. Remove trailing slash EXCEPT for root (/)
        5. Keep query parameters as-is (filtered)
        
        Returns None if URL should be skipped
        """
        try:
            parsed = urlparse(url.strip())
            
            # 1. Preserve original scheme (don't force HTTPS)
            scheme = (parsed.scheme or 'https').lower()
            
            # 2. Lowercase hostname and remove default ports
            netloc = parsed.netloc.lower()
            # Remove default ports
            if netloc.endswith(':80') and scheme == 'http':
                netloc = netloc[:-3]
            elif netloc.endswith(':443') and scheme == 'https':
                netloc = netloc[:-4]
            
            # 3. Normalize path - CRITICAL for duplicate detection
            path = parsed.path or '/'
            
            # Remove trailing slash EXCEPT for root
            # This is industry standard and prevents duplicate URLs
            if path != '/' and path.endswith('/'):
                path = path.rstrip('/')
            
            # 4. Handle query parameters
            query = ''
            if not remove_query and parsed.query:
                query_params = parse_qs(parsed.query)
                # Remove tracking and pagination params
                clean_params = {
                    k: v for k, v in query_params.items() 
                    if k.lower() not in URLNormalizer.TRACKING_PARAMS 
                    and k.lower() not in URLNormalizer.SKIP_PARAMS
                }
                if clean_params:
                    query = '&'.join(f"{k}={v[0]}" for k, v in sorted(clean_params.items()))
            
            # 5. Reconstruct without fragment (fragment always removed)
            normalized = urlunparse((scheme, netloc, path, '', query, ''))
            
            return normalized
            
        except Exception as e:
            logger.error(f"URL normalization error for {url}: {e}")
            return None
    
    @staticmethod
    def get_url_hash(url: str) -> str:
        """Generate consistent hash for URL deduplication"""
        return hashlib.md5(url.encode()).hexdigest()
    
    @staticmethod
    def has_query_params(url: str) -> bool:
        """Check if URL has query parameters"""
        parsed = urlparse(url)
        return bool(parsed.query)
    
    @staticmethod
    def should_skip(url: str) -> bool:
        """Check if URL should be skipped based on patterns"""
        skip_patterns = [
            r'/wp-admin', r'/wp-login', r'/admin',
            r'/cart', r'/checkout', r'/account', r'/profile',
            r'\.(pdf|jpg|jpeg|png|gif|css|js|ico|svg|woff|ttf|zip|exe)$',
            r'/feed/', r'/rss', r'/xmlrpc\.php',
            r'/wp-content/', r'/wp-includes/',
            r'/api/', r'/ajax/'
        ]
        
        url_lower = url.lower()
        return any(re.search(pattern, url_lower) for pattern in skip_patterns)
    
    @staticmethod
    def get_pagination_cluster_id(url: str) -> Optional[str]:
        """Generate cluster ID for pagination detection (removes page params)"""
        try:
            parsed = urlparse(url)
            query_params = parse_qs(parsed.query)
            
            # Remove pagination parameters
            pagination_params = {'page', 'p', 'offset', 'paged', 'pg'}
            clean_params = {k: v for k, v in query_params.items() 
                          if k.lower() not in pagination_params}
            
            # Reconstruct URL without pagination params
            clean_query = '&'.join(f"{k}={v[0]}" for k, v in sorted(clean_params.items()))
            base_url = urlunparse((parsed.scheme, parsed.netloc, parsed.path, '', clean_query, ''))
            
            # Return hash of base URL
            return hashlib.md5(base_url.encode()).hexdigest()
        except:
            return None


class PageClassifier:
    """Intelligent page type classification"""
    
    @staticmethod
    def classify(url: str, title: Optional[str], h1: Optional[str], 
                 status_code: int, word_count: int, has_params: bool = False,
                 link_density: float = 0.0) -> Tuple[PageType, bool, Optional[str]]:
        """
        Classify page type and determine base indexability
        Returns: (page_type, indexable, reason)
        
        IMPORTANT: Crawler observes, doesn't judge.
        Only mark non-indexable if truly blocked (robots/noindex/status).
        Thin content, auth, legal pages ARE indexable - audit engine decides quality.
        """
        url_lower = url.lower()
        title_lower = (title or "").lower()
        h1_lower = (h1 or "").lower()
        
        # ERROR PAGES (rely primarily on status code)
        if status_code != 200:
            return PageType.ERROR, False, f"status_{status_code}"
        
        # Secondary error detection via content (fallback only)
        if ('404' in h1_lower or '404' in title_lower or 
            'not found' in h1_lower or 'page not found' in title_lower):
            return PageType.ERROR, False, "error_page"
        
        # SPECIALIZED PAGE TYPES (Priority 3)
        
        # DOCS INDEX - Documentation navigation pages
        docs_patterns = ['/docs', '/documentation', '/guide', '/tutorial']
        if any(pattern in url_lower for pattern in docs_patterns):
            # High link density + low word count = likely index page
            if link_density > 0.3 and word_count < 300:
                return PageType.DOCS_INDEX, True, None
        
        # API REFERENCE - API documentation
        api_patterns = ['/api/', '/reference/', '/api-reference']
        if any(pattern in url_lower for pattern in api_patterns):
            return PageType.API_REFERENCE, True, None
        
        # GLOSSARY - Definition pages
        glossary_patterns = ['/glossary', '/definitions', '/terminology']
        if any(pattern in url_lower for pattern in glossary_patterns):
            return PageType.GLOSSARY, True, None
        
        # QUERY PARAMETER UTILITY PAGES (e.g., /auth?view=signin)
        if has_params:
            param_utility_patterns = ['/auth', '/account', '/profile', '/user']
            if any(pattern in url_lower for pattern in param_utility_patterns):
                return PageType.UTILITY, False, "utility_page"
        
        # AUTH PAGES (indexable but low SEO priority)
        auth_patterns = ['/auth', '/login', '/signup', '/signin', '/register', 
                        '/sign-in', '/sign-up', '/logout']
        if any(pattern in url_lower for pattern in auth_patterns):
            return PageType.AUTH, True, None
        
        # LEGAL PAGES (indexable but low SEO priority)
        legal_patterns = ['/terms', '/privacy', '/cookie', '/legal', 
                         '/disclaimer', '/gdpr']
        if any(pattern in url_lower for pattern in legal_patterns):
            return PageType.LEGAL, True, None
        
        # UTILITY PAGES (truly non-indexable)
        utility_patterns = ['/search', '/cart', '/checkout', '/contact-form']
        if any(pattern in url_lower for pattern in utility_patterns):
            return PageType.UTILITY, False, "utility_page"
        
        # CONTENT PAGE (including thin content - let audit engine judge quality)
        return PageType.CONTENT, True, None
    
    @staticmethod
    def filter_internal_links(links: List[str]) -> List[str]:
        """Filter out non-content internal links"""
        filtered = []
        for link in links:
            link_lower = link.lower()
            
            # Skip auth, utility, and admin links
            skip_patterns = [
                '/auth', '/login', '/signup', '/signin', '/logout',
                '/cart', '/checkout', '/account', '/profile',
                '/admin', '/wp-admin'
            ]
            
            if not any(pattern in link_lower for pattern in skip_patterns):
                filtered.append(link)
        
        return filtered


class RobotsTxtChecker:
    """Handles robots.txt compliance"""
    
    def __init__(self, user_agent: str = "*"):
        self.user_agent = user_agent
        self.parsers: Dict[str, robotparser.RobotFileParser] = {}
    
    def can_crawl(self, url: str) -> bool:
        """Check if URL can be crawled according to robots.txt"""
        try:
            parsed = urlparse(url)
            base_url = f"{parsed.scheme}://{parsed.netloc}"
            
            if base_url not in self.parsers:
                rp = robotparser.RobotFileParser()
                robots_url = f"{base_url}/robots.txt"
                rp.set_url(robots_url)
                try:
                    rp.read()
                    self.parsers[base_url] = rp
                    logger.info(f"Loaded robots.txt from {robots_url}")
                except Exception as e:
                    logger.warning(f"Could not read robots.txt for {base_url}: {e}")
                    # If robots.txt doesn't exist, allow crawling
                    return True
            
            return self.parsers[base_url].can_fetch(self.user_agent, url)
            
        except Exception as e:
            logger.error(f"Robots.txt check error for {url}: {e}")
            return True


class ContentExtractor:
    """Advanced content extraction with main content isolation"""
    
    @staticmethod
    def extract_main_content(soup: BeautifulSoup) -> Tuple[str, int]:
        """
        Extract main content only, excluding boilerplate
        Returns: (main_content_text, word_count)
        """
        # Priority 1: <main> tag
        main_tag = soup.find('main')
        if main_tag:
            return ContentExtractor._clean_text(main_tag)
        
        # Priority 2: <article> tag
        article_tag = soup.find('article')
        if article_tag:
            return ContentExtractor._clean_text(article_tag)
        
        # Priority 3: Role="main"
        role_main = soup.find(attrs={"role": "main"})
        if role_main:
            return ContentExtractor._clean_text(role_main)
        
        # Priority 4: Largest content block heuristic
        # Find divs with most text content
        content_blocks = []
        for div in soup.find_all(['div', 'section']):
            # Skip navigation, header, footer
            if div.find_parent(['nav', 'header', 'footer']):
                continue
            
            text = div.get_text(strip=True)
            if len(text) > 200:  # Minimum meaningful content
                content_blocks.append((div, len(text)))
        
        if content_blocks:
            # Get the largest block
            largest_block = max(content_blocks, key=lambda x: x[1])
            return ContentExtractor._clean_text(largest_block[0])
        
        # Fallback: body content
        body = soup.find('body')
        if body:
            return ContentExtractor._clean_text(body)
        
        return "", 0
    
    @staticmethod
    def _clean_text(element) -> Tuple[str, int]:
        """Clean and count words in element"""
        # Remove script, style, nav, footer, header, form
        for tag in element(['script', 'style', 'nav', 'footer', 'header', 'form', 'aside']):
            tag.decompose()
        
        text = element.get_text(separator=" ")
        text = re.sub(r'\s+', ' ', text).strip()
        words = re.findall(r'\b\w+\b', text)
        
        return text[:5000], len(words)
    
    @staticmethod
    def calculate_link_density(soup, main_content_text: str) -> float:
        """
        Calculate link density (ratio of link text to total text)
        Used for thin content exceptions (navigation pages, etc.)
        """
        if not main_content_text or len(main_content_text) == 0:
            return 0.0
        
        # Get all link text
        links = soup.find_all('a', href=True)
        link_text_length = sum(len(link.get_text(strip=True)) for link in links)
        total_text_length = len(main_content_text)
        
        if total_text_length == 0:
            return 0.0
        
        return round(link_text_length / total_text_length, 3)


class SEOExtractor:
    """Enhanced SEO data extraction with intelligence"""
    
    @staticmethod
    def extract(html: str, url: str) -> Dict[str, Any]:
        """Extract all SEO data with enhanced intelligence"""
        soup = BeautifulSoup(html, "lxml")
        
        # Meta robots
        noindex = False
        nofollow = False
        robots_meta = soup.find("meta", attrs={"name": re.compile("robots", re.I)})
        if robots_meta:
            content = robots_meta.get("content", "").lower()
            noindex = "noindex" in content
            nofollow = "nofollow" in content
        
        # Canonical
        canonical = soup.find("link", rel="canonical")
        canonical_url = canonical.get("href") if canonical else url
        
        # Title
        title = None
        if soup.title and soup.title.string:
            title = soup.title.string.strip()
        
        # Meta description
        meta_desc = soup.find("meta", attrs={"name": re.compile("description", re.I)})
        meta_description = meta_desc.get("content", "").strip() if meta_desc else None
        
        # Headings
        h1 = soup.find("h1")
        h1_text = h1.get_text(strip=True) if h1 else None
        
        h2_list = [h.get_text(strip=True) for h in soup.find_all("h2")]
        h3_list = [h.get_text(strip=True) for h in soup.find_all("h3")]
        
        # NEW: Count headings for Content Quality Analyzer
        h1_count = len(soup.find_all("h1"))
        h2_count = len(h2_list)
        h3_count = len(h3_list)
        
        # Main content extraction
        main_content_text, main_word_count = ContentExtractor.extract_main_content(soup)
        
        # Full content (for comparison)
        full_soup = BeautifulSoup(html, "lxml")
        for script in full_soup(["script", "style"]):
            script.decompose()
        full_text = full_soup.get_text(separator=" ")
        full_text = re.sub(r'\s+', ' ', full_text).strip()
        full_words = re.findall(r'\b\w+\b', full_text)
        total_word_count = len(full_words)

        # Calculate boilerplate
        boilerplate_count = max(0, total_word_count - main_word_count)

        # Links with context tracking
        internal_links = []
        external_links = []
        base_domain = urlparse(url).netloc

        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if not href or href.startswith('#'):
                continue

            absolute = urljoin(url, href)
            link_domain = urlparse(absolute).netloc

            # Detect link context based on parent elements
            context = SEOExtractor._detect_link_context(a)

            link_obj = {
                "url": absolute,
                "context": context
            }

            if link_domain == base_domain:
                internal_links.append(link_obj)
            else:
                external_links.append(link_obj)

        # FIXED: Normalize links BEFORE deduplication
        normalized_internal = {}
        for link_obj in internal_links:
            normalized = URLNormalizer.normalize(link_obj["url"], base_domain)
            if normalized:
                # Keep first occurrence of each URL (preserves context)
                if normalized not in normalized_internal:
                    normalized_internal[normalized] = link_obj["context"]

        # Convert back to list of objects
        internal_links_normalized = [
            {"url": url_str, "context": context}
            for url_str, context in normalized_internal.items()
        ]

        # Deduplicate external links
        external_links_deduplicated = []
        seen_external_urls = set()
        for link_obj in external_links:
            if link_obj["url"] not in seen_external_urls:
                external_links_deduplicated.append(link_obj)
                seen_external_urls.add(link_obj["url"])
        external_links = external_links_deduplicated[:50]


        # Filter internal links (remove auth, utility)
        # Pass only URLs to the filter function
        internal_urls_for_filter = [link["url"] for link in internal_links_normalized]
        filtered_urls = PageClassifier.filter_internal_links(internal_urls_for_filter)
        # Reconstruct filtered links with context (if original context is desired)
        # For simplicity, we'll just store the filtered URLs here.
        # If context is needed for filtered links, a more complex mapping would be required.
        internal_links_filtered = filtered_urls

        # Meta robots tag content
        meta_robots_content = None
        if robots_meta:
            meta_robots_content = robots_meta.get("content", "")

        # Hreflang
        hreflang_links = []
        for link in soup.find_all("link", rel="alternate", hreflang=True):
            hreflang_links.append(link.get("href", ""))

        # Pagination (rel=next/prev)
        pagination_rel = None
        next_link = soup.find("link", rel="next")
        prev_link = soup.find("link", rel="prev")
        if next_link:
            pagination_rel = "next"
        elif prev_link:
            pagination_rel = "prev"

        # Calculate link density
        link_text_length = sum(len(a.get_text(strip=True)) for a in soup.find_all("a"))
        total_text_length = len(main_content_text) if main_content_text else 1
        link_density = link_text_length / total_text_length if total_text_length > 0 else 0.0

        return {
            "title": title,
            "meta_description": meta_description,
            "h1": h1_text,
            "h2": h2_list,
            "h3": h3_list,
            "h1_count": h1_count,  # NEW
            "h2_count": h2_count,  # NEW
            "h3_count": h3_count,  # NEW
            "content": full_text[:5000], # Keep original truncation
            "main_content": main_content_text,
            "word_count_raw": total_word_count,
            "word_count_main": main_word_count,
            "boilerplate_word_count": boilerplate_count,
            "internal_links": internal_links_normalized,  # Now with context
            "internal_links_filtered": internal_links_filtered,  # URLs only
            "external_links": external_links, # Now with context
            "canonical_url": canonical_url,
            "noindex": noindex,
            "nofollow": nofollow,
            "meta_robots": meta_robots_content,
            "hreflang": hreflang_links,
            "pagination_rel": pagination_rel,
            "link_density": link_density
        }

    @staticmethod
    def _detect_link_context(link_element) -> str:
        """
        Detect link context based on parent elements

        Returns:
            "nav" - Navigation/header links
            "footer" - Footer links
            "breadcrumb" - Breadcrumb links
            "content" - Main content links (default)
        """
        # Check parent elements up to 5 levels
        current = link_element
        for _ in range(5):
            if current.parent is None:
                break

            current = current.parent

            # Check tag name
            tag_name = current.name if hasattr(current, 'name') else ''

            # Check for nav/header
            if tag_name in ['nav', 'header']:
                return "nav"

            # Check for footer
            if tag_name == 'footer':
                return "footer"

            # Check class/id attributes
            if hasattr(current, 'get'):
                class_attr = ' '.join(current.get('class', [])).lower()
                id_attr = (current.get('id', '') or '').lower()

                # Navigation patterns
                nav_patterns = ['nav', 'menu', 'header', 'sidebar', 'aside']
                if any(pattern in class_attr or pattern in id_attr for pattern in nav_patterns):
                    return "nav"

                # Footer patterns
                if 'footer' in class_attr or 'footer' in id_attr:
                    return "footer"

                # Breadcrumb patterns
                breadcrumb_patterns = ['breadcrumb', 'crumb']
                if any(pattern in class_attr or pattern in id_attr for pattern in breadcrumb_patterns):
                    return "breadcrumb"

        # Default to content
        return "content"


class PageFetcher:
    """Handles page fetching with Playwright"""
    
    def __init__(self, user_agent: str = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"):
        self.user_agent = user_agent
        self.playwright = None
        self.browser = None
    
    def __enter__(self):
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=True)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()
    
    def fetch(self, url: str, timeout: int = 30000) -> tuple[Optional[str], Optional[int], Optional[str], List[Dict[str, Any]], Optional[int]]:
        """Fetch page HTML and status code with redirect tracking"""
        redirect_chain = []
        current_url = url
        final_html = None
        final_status = None
        max_redirects = 10
        
        try:
            for hop in range(max_redirects):
                page = self.browser.new_page(user_agent=self.user_agent)
                
                # Block unnecessary resources
                page.route("**/*", lambda route: route.abort() 
                          if route.request.resource_type in ["image", "media", "font"] 
                          else route.continue_())
                
                # Navigate without following redirects automatically
                response = page.goto(current_url, timeout=timeout, wait_until="domcontentloaded")
                
                if response:
                    status = response.status
                    
                    # Check if this is a redirect
                    if 300 <= status < 400:
                        # Record this hop
                        redirect_chain.append({
                            "url": current_url,
                            "status": status
                        })
                        
                        # Get redirect location from headers
                        headers = response.headers
                        location = headers.get('location')
                        
                        if location:
                            # Handle relative redirects
                            from urllib.parse import urljoin
                            next_url = urljoin(current_url, location)
                            page.close()
                            current_url = next_url
                            continue
                        else:
                            # No location header, treat as final
                            page.close()
                            break
                    else:
                        # Not a redirect, this is the final page
                        page.wait_for_timeout(1000)
                        final_html = page.content()
                        final_status = status
                        page.close()
                        break
                else:
                    page.close()
                    break
            
            # Determine redirect_to (first redirect target)
            redirect_to = redirect_chain[0]["url"] if redirect_chain else None
            
            return final_html, final_status, redirect_to, redirect_chain, final_status
            
        except PlaywrightTimeout:
            logger.warning(f"Timeout fetching {url}")
            return None, None, None, [], None
        except Exception as e:
            logger.error(f"Error fetching {url}: {e}")
            return None, None, None, [], None


class EnterpriseCrawler:
    """Enhanced crawler with intelligent page classification"""
    
    def __init__(
        self,
        max_pages: int = 200,
        rate_limit: float = 1.0,
        output_dir: str = "crawler_output",
        user_agent: str = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
    ):
        self.max_pages = max_pages
        self.rate_limit = rate_limit
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        
        self.normalizer = URLNormalizer()
        self.robots_checker = RobotsTxtChecker(user_agent)
        self.classifier = PageClassifier()
        self.user_agent = user_agent
        self.base_domain = None  # Set during crawl
        
        self.visited: Set[str] = set()
        self.queue: deque = deque()  # Now stores (url, depth) tuples
        self.results: List[PageData] = []
        self.errors: List[Dict] = []
        self.robots_blocked: int = 0
    
    def _generate_url_variants(self, url: str) -> List[str]:
        """Generate URL variants to test for redirects"""
        variants = [url]
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
        
        # Remove duplicates and return
        return list(set(variants))
    
    def crawl(self, start_url: str) -> Dict[str, Any]:
        """Main crawl entry point with enhanced intelligence"""
        logger.info(f"🚀 Starting intelligent crawl of {start_url}")
        start_time = time.time()
        
        # Normalize start URL
        normalized_start = self.normalizer.normalize(start_url, start_url)
        if not normalized_start:
            raise ValueError(f"Invalid start URL: {start_url}")
        
        self.queue.append((normalized_start, 0))  # Start at depth 0
        base_domain = urlparse(normalized_start).netloc
        self.base_domain = base_domain
        
        with PageFetcher(self.user_agent) as fetcher:
            while self.queue and len(self.results) < self.max_pages:
                url, depth = self.queue.popleft()
                
                # Skip if already visited (using normalized URL)
                normalized_url = self.normalizer.normalize(url, base_domain)
                if not normalized_url:
                    continue
                
                url_hash = self.normalizer.get_url_hash(normalized_url)
                if url_hash in self.visited:
                    continue
                
                self.visited.add(url_hash)
                
                # Process URL
                self._process_url(normalized_url, base_domain, fetcher, depth)
                
                # Rate limiting
                time.sleep(self.rate_limit)
                
                logger.info(f"📊 Progress: {len(self.results)}/{self.max_pages} pages | "
                          f"Queue: {len(self.queue)}")
        
        # Save results
        duration = time.time() - start_time
        summary = self._save_results(start_url, duration)
        
        logger.info(f"✅ Crawl completed: {len(self.results)} pages in {duration:.2f}s")
        return summary
    
    def _process_url(self, url: str, base_domain: str, fetcher: PageFetcher, depth: int = 0):
        """Process a single URL with full intelligence"""
        try:
            # Normalize URL for hash generation
            normalized_url = self.normalizer.normalize(url, base_domain)
            if not normalized_url:
                return
            
            url_hash = self.normalizer.get_url_hash(normalized_url)
            
            # FIXED: Check skip patterns BEFORE robots check (avoid unnecessary robots hits)
            if self.normalizer.should_skip(url):
                logger.info(f"⏭️  Skipped by pattern: {url}")
                return
            
            # Check robots.txt (but still store the page for audit)
            blocked_by_robots = not self.robots_checker.can_crawl(url)
            if blocked_by_robots:
                logger.info(f"🚫 Blocked by robots.txt: {url}")
                self.robots_blocked += 1
                # FIXED: Don't return - continue processing to store blocked page
            
            # Fetch page (skip if blocked by robots)
            if blocked_by_robots:
                html, status, redirect_to, redirect_chain, final_status = None, None, None, [], None
            else:
                html, status, redirect_to, redirect_chain, final_status = fetcher.fetch(url)
            
            if not html and not blocked_by_robots:
                self.errors.append({
                    "url": url,
                    "status": status,
                    "error": "Failed to fetch"
                })
                return
            
            # Extract SEO data (only if we have HTML)
            if html:
                seo_data = SEOExtractor.extract(html, url)
            else:
                # Minimal data for robots-blocked pages
                seo_data = {
                    "title": None,
                    "meta_description": None,
                    "h1": None,
                    "h2": [],
                    "h3": [],
                    "h1_count": 0,  # NEW
                    "h2_count": 0,  # NEW
                    "h3_count": 0,  # NEW
                    "content": "",
                    "main_content": "",
                    "word_count_raw": 0,
                    "word_count_main": 0,
                    "boilerplate_word_count": 0,
                    "link_density": 0.0,
                    "internal_links": [],
                    "internal_links_filtered": [],
                    "external_links": [],
                    "canonical_url": url,
                    "meta_robots": None,
                    "hreflang": [],
                    "pagination_rel": None,
                    "noindex": False,
                    "nofollow": False
                }
            
            # Check if URL has query parameters
            url_has_params = self.normalizer.has_query_params(url)
            
            # FIXED: Robots-blocked pages should not be classified as ERROR
            # Use status 200 for classification if blocked by robots
            status_for_classification = status if status is not None else (200 if blocked_by_robots else 0)
            
            # Classify page type and base indexability
            page_type, base_indexable, reason = self.classifier.classify(
                url=url,
                title=seo_data["title"],
                h1=seo_data["h1"],
                status_code=status_for_classification,
                word_count=seo_data["word_count_main"],
                has_params=url_has_params,
                link_density=seo_data["link_density"]
            )
            
            # FIXED: Force robots-blocked pages to UTILITY type
            if blocked_by_robots:
                page_type = PageType.UTILITY
                base_indexable = False
                reason = "blocked_by_robots"
            
            # CANONICAL CLASSIFICATION (Priority 1 - Highest Impact)
            # Distinguish between intentional consolidations and actual issues
            canonical_url = seo_data["canonical_url"]
            
            # FIXED: Robots-blocked pages - set canonical to unknown
            if blocked_by_robots:
                canonical_type = "unknown"
                canonical_non_self = False
                canonical_intentional = False
            else:
                # FIXED: Handle relative canonical URLs with urljoin
                canonical_absolute = urljoin(url, canonical_url) if canonical_url else url
                canonical_normalized = self.normalizer.normalize(canonical_absolute, base_domain)
                
                # FIXED: Homepage canonical edge case
                # If canonical is / and normalized is https://domain.com, treat as same
                if canonical_normalized and canonical_normalized.endswith('/'):
                    canonical_normalized_no_slash = canonical_normalized.rstrip('/')
                    if canonical_normalized_no_slash == normalized_url:
                        canonical_normalized = normalized_url
                
                canonical_non_self = (canonical_normalized != normalized_url)
            
                # Detect protocol mismatch (HTTP vs HTTPS)
                url_scheme = urlparse(normalized_url).scheme
                canonical_scheme = urlparse(canonical_normalized).scheme if canonical_normalized else url_scheme
                protocol_mismatch = (url_scheme != canonical_scheme) if canonical_normalized else False
                
                # Classify canonical type
                if not canonical_url or canonical_url.strip() == "":
                    canonical_type = "missing"
                    canonical_non_self = True
                    canonical_intentional = False
                elif canonical_normalized == normalized_url:
                    canonical_type = "self"  # Correct self-referencing canonical
                    canonical_non_self = False
                    canonical_intentional = False
                else:
                    # Canonical points elsewhere - is it intentional or broken?
                    # Check if canonical target is internal and exists in our crawl
                    canonical_domain = urlparse(canonical_normalized).netloc if canonical_normalized else ""
                    is_internal = (canonical_domain == base_domain)
                    
                    if is_internal:
                        # Internal canonical - likely intentional consolidation
                        canonical_type = "consolidation"
                        canonical_non_self = True
                        canonical_intentional = True  # Prevents audit over-penalization
                    else:
                        # External canonical or broken - definite issue
                        canonical_type = "issue"
                        canonical_non_self = True
                        canonical_intentional = False
            
            # Detect homepage
            parsed_url = urlparse(normalized_url)
            is_homepage = (normalized_url.rstrip('/') == f"{parsed_url.scheme}://{parsed_url.netloc}")
            
            # Generate pagination cluster ID
            pagination_cluster_id = self.normalizer.get_pagination_cluster_id(url) if seo_data.get("pagination_rel") else None
            
            # INDEXABILITY LOGIC
            # Canonical issues are ranking problems, NOT indexability blocks
            # Only these make a page non-indexable:
            # 1. Blocked by robots.txt
            # 2. noindex meta tag
            # 3. HTTP status != 200
            # 4. Page type is ERROR or UTILITY
            indexable = base_indexable
            indexability_reason = reason
            
            if blocked_by_robots:
                indexable = False
                indexability_reason = "blocked_by_robots"
            elif seo_data["noindex"]:
                indexable = False
                indexability_reason = "noindex_meta"
            elif status != 200 and status is not None:
                indexable = False
                indexability_reason = f"status_{status}"
            
            # SEO ELIGIBILITY CALCULATION
            # Canonical issues affect SEO eligibility, NOT indexability
            # SEO-eligible = should be scored and optimized by audit engine
            
            # THIN CONTENT EXCEPTION (Priority 2)
            # Navigation pages, docs indexes, glossaries can be thin but valuable
            thin_content_exception = False
            is_thin = seo_data["word_count_main"] < 100
            
            if is_thin:
                # Exception 1: High link density (navigation/index pages)
                if seo_data["link_density"] > 0.3:
                    thin_content_exception = True
                
                # Exception 2: Specialized page types
                if page_type in [PageType.DOCS_INDEX, PageType.GLOSSARY, PageType.API_REFERENCE]:
                    thin_content_exception = True
            
            seo_eligible = (
                indexable
                and page_type == PageType.CONTENT
                and not canonical_non_self  # RENAMED from canonical_issue
                and (seo_data["word_count_main"] >= 100 or thin_content_exception)
            )
            
            # Create enhanced PageData
            page = PageData(
                url=url,
                normalized_url=normalized_url,
                original_url=url,  # NEW: Track original URL
                discovered_from="",  # NEW: Will be populated when discovered via links
                domain=base_domain,
                status_code=status if status is not None else (403 if blocked_by_robots else 0),
                is_homepage=is_homepage,
                crawl_depth=depth,
                title=seo_data["title"],
                meta_description=seo_data["meta_description"],
                h1=seo_data["h1"],
                h2=seo_data["h2"],
                h3=seo_data["h3"],
                h1_count=seo_data["h1_count"],  # NEW
                h2_count=seo_data["h2_count"],  # NEW
                h3_count=seo_data["h3_count"],  # NEW
                content=seo_data["content"],
                main_content=seo_data["main_content"],
                word_count_raw=seo_data["word_count_raw"],
                word_count_main=seo_data["word_count_main"],
                boilerplate_word_count=seo_data["boilerplate_word_count"],
                link_density=seo_data["link_density"],
                thin_content_exception=thin_content_exception,
                internal_links=seo_data["internal_links"],
                internal_links_filtered=seo_data["internal_links_filtered"],
                external_links=seo_data["external_links"],
                canonical_url=canonical_url,
                canonical_target=canonical_normalized if canonical_non_self else None,
                canonical_non_self=canonical_non_self,
                canonical_type=canonical_type,
                canonical_intentional=canonical_intentional,
                protocol_mismatch=protocol_mismatch if not blocked_by_robots else False,
                url_has_params=url_has_params,
                meta_robots=seo_data["meta_robots"],
                hreflang=seo_data["hreflang"],
                pagination_rel=seo_data["pagination_rel"],
                pagination_cluster_id=pagination_cluster_id,
                noindex=seo_data["noindex"],
                nofollow=seo_data["nofollow"],
                blocked_by_robots=blocked_by_robots,
                redirect_to=redirect_to,
                redirect_chain=redirect_chain if redirect_chain else [],
                final_url=url if not redirect_chain else (redirect_chain[-1]["url"] if redirect_chain else url),
                final_status=final_status,
                page_type=page_type.value,
                indexable=indexable,
                indexability_reason=indexability_reason,
                seo_eligible=seo_eligible,
                crawled_at=datetime.utcnow().isoformat(),
                url_hash=url_hash
            )
            
            self.results.append(page)
            
            logger.info(f"✓ {page_type.value.upper()}: {url} "
                       f"({seo_data['word_count_main']} words, {seo_data['link_density']:.1%} links) "
                       f"{'✅ indexable' if indexable else '❌ ' + (indexability_reason or '')} "
                       f"{'🎯 SEO-eligible' if seo_eligible else ''} "
                       f"{'⚠️ canonical-' + canonical_type if canonical_non_self else ''} "
                       f"{'✨ thin-exception' if thin_content_exception else ''}")
            
            # Add filtered internal links to queue (skip if blocked by robots)
            if not blocked_by_robots:
                for link in seo_data["internal_links_filtered"]:
                    normalized_link = self.normalizer.normalize(link, base_domain)
                    if normalized_link:
                        link_domain = urlparse(normalized_link).netloc
                        if link_domain == base_domain:
                            link_hash = self.normalizer.get_url_hash(normalized_link)
                            if link_hash not in self.visited and len(self.results) < self.max_pages:
                                self.queue.append((normalized_link, depth + 1))  # Increment depth
        
        except Exception as e:
            logger.error(f"❌ Error processing {url}: {e}")
            self.errors.append({
                "url": url,
                "error": str(e)
            })
    
    def _save_results(self, start_url: str, duration: float) -> Dict[str, Any]:
        """Save enhanced crawl results with factual summary (no SEO opinions)"""
        domain = urlparse(start_url).netloc.replace('.', '_')
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        
        # Calculate factual metrics (crawler observes, doesn't judge)
        indexable_pages = [p for p in self.results if p.indexable]
        seo_eligible_pages = [p for p in self.results if p.seo_eligible]
        content_pages = [p for p in self.results if p.page_type == PageType.CONTENT.value]
        canonical_non_self_pages = [p for p in self.results if p.canonical_non_self]
        canonical_consolidations = [p for p in self.results if p.canonical_type == "consolidation"]
        canonical_real_issues = [p for p in self.results if p.canonical_type == "issue"]
        
        # Save pages data
        pages_file = self.output_dir / f"{domain}_{timestamp}_pages.json"
        with open(pages_file, 'w', encoding='utf-8') as f:
            json.dump(
                [page.to_dict() for page in self.results],
                f,
                indent=2,
                ensure_ascii=False
            )
        
        # Save errors
        errors_file = self.output_dir / f"{domain}_{timestamp}_errors.json"
        with open(errors_file, 'w', encoding='utf-8') as f:
            json.dump(self.errors, f, indent=2)
        
        # Create factual summary (let audit engine compute weighted metrics)
        summary = {
            "domain": start_url,
            "crawl_started": timestamp,
            "duration_seconds": round(duration, 2),
            "pages_crawled": len(self.results),
            "errors": len(self.errors),
            "robots_blocked_count": self.robots_blocked,
            "pages_file": str(pages_file),
            "errors_file": str(errors_file),
            
            # FACTUAL SUMMARY (Crawler = facts, Audit = decisions)
            "crawl_summary": {
                "total_pages": len(self.results),
                "indexable_pages": len(indexable_pages),
                "seo_eligible_pages": len(seo_eligible_pages),  # NEW
                "content_pages": len(content_pages),
                "non_indexable_pages": len(self.results) - len(indexable_pages),
                "canonical_non_self": len(canonical_non_self_pages),
                "canonical_breakdown": {
                    "self": len([p for p in self.results if p.canonical_type == "self"]),
                    "consolidation": len(canonical_consolidations),
                    "issue": len(canonical_real_issues),
                    "missing": len([p for p in self.results if p.canonical_type == "missing"]),
                    "unknown": len([p for p in self.results if p.canonical_type == "unknown"])
                },
                # REMOVED: avg_main_content_word_count (let audit engine decide weighting)
                "pages_by_type": {
                    "content": len([p for p in self.results if p.page_type == "content"]),
                    "auth": len([p for p in self.results if p.page_type == "auth"]),
                    "legal": len([p for p in self.results if p.page_type == "legal"]),
                    "error": len([p for p in self.results if p.page_type == "error"]),
                    "utility": len([p for p in self.results if p.page_type == "utility"]),
                    "docs_index": len([p for p in self.results if p.page_type == "docs_index"]),
                    "api_reference": len([p for p in self.results if p.page_type == "api_reference"]),
                    "glossary": len([p for p in self.results if p.page_type == "glossary"])
                },
                "pages_by_indexability": {
                    "indexable": len(indexable_pages),
                    "seo_eligible": len(seo_eligible_pages),
                    "blocked_by_robots": len([p for p in self.results if p.blocked_by_robots]),
                    "noindex": len([p for p in self.results if p.noindex]),
                    "thin_content": len([p for p in content_pages if p.word_count_main < 100]),
                    "thin_with_exception": len([p for p in self.results if p.thin_content_exception]),
                    "with_query_params": len([p for p in self.results if p.url_has_params])
                }
            },
            
            # Legacy statistics (for compatibility)
            "statistics": {
                "avg_word_count_raw": round(
                    sum(p.word_count_raw for p in self.results) / len(self.results)
                    if self.results else 0, 1
                ),
                "avg_word_count_main": round(
                    sum(p.word_count_main for p in self.results) / len(self.results)
                    if self.results else 0, 1
                ),
                "pages_with_h1": sum(1 for p in self.results if p.h1),
                "pages_with_meta_desc": sum(1 for p in self.results if p.meta_description),
                "total_internal_links": sum(len(p.internal_links_filtered) for p in self.results),
                "indexable_pages": len(indexable_pages)
            }
        }
        
        # Save summary
        summary_file = self.output_dir / f"{domain}_{timestamp}_summary.json"
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2)
        
        # Print factual summary
        print("\n" + "="*70)
        print("🎯 CRAWL SUMMARY (Factual Observations)")
        print("="*70)
        print(f"Total Pages: {len(self.results)}")
        print(f"✅ Indexable: {len(indexable_pages)}")
        print(f"🎯 SEO-Eligible: {len(seo_eligible_pages)}")
        print(f"⚠️  Canonical Non-Self: {len(canonical_non_self_pages)}")
        print(f"    ├─ Consolidations (intentional): {len(canonical_consolidations)}")
        print(f"    └─ Real Issues (need fixing): {len(canonical_real_issues)}")
        print(f"🚫 Blocked by Robots: {summary['crawl_summary']['pages_by_indexability']['blocked_by_robots']}")
        print("="*70 + "\n")
        
        return summary


# Example usage
if __name__ == "__main__":
    crawler = EnterpriseCrawler(
        max_pages=100,
        rate_limit=1.0,
        output_dir="crawler_output"
    )
    
    summary = crawler.crawl("https://developer.mozilla.org/en-US/")
    print(json.dumps(summary, indent=2))