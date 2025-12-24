"""
Enterprise SEO Audit Rules Engine v2.0
Compatible with Crawler v2.0 - Intelligent page classification
"""

import json
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from enum import Enum
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
import re
from urllib.parse import urlparse


class Severity(Enum):
    """Issue severity levels"""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class Category(Enum):
    """SEO audit categories"""
    TECHNICAL = "technical"
    CONTENT = "content"
    META_TAGS = "meta_tags"
    STRUCTURE = "structure"
    LINKS = "links"
    PERFORMANCE = "performance"


@dataclass
class SEOIssue:
    """Represents a single SEO issue"""
    rule_id: str
    title: str
    severity: Severity
    category: Category
    description: str
    impact: str
    affected_pages: List[str]
    affected_count: int
    recommendation: str
    how_to_fix: str
    priority_score: int = 0
    
    def to_dict(self) -> Dict:
        return {
            "rule_id": self.rule_id,
            "title": self.title,
            "severity": self.severity.value,
            "category": self.category.value,
            "description": self.description,
            "impact": self.impact,
            "affected_pages": self.affected_pages[:10],
            "affected_count": self.affected_count,
            "recommendation": self.recommendation,
            "how_to_fix": self.how_to_fix,
            "priority_score": self.priority_score
        }


@dataclass
class AuditStats:
    """Overall audit statistics"""
    total_pages: int = 0
    indexable_pages: int = 0
    content_pages: int = 0
    critical_issues: int = 0
    high_issues: int = 0
    medium_issues: int = 0
    low_issues: int = 0
    info_issues: int = 0
    seo_score: int = 0
    pages_with_issues: int = 0
    avg_word_count: float = 0
    total_issues: int = 0


class SEOAuditEngine:
    """Enhanced SEO audit engine compatible with Crawler v2.0"""
    
    def __init__(self):
        self.issues: List[SEOIssue] = []
        self.stats = AuditStats()
        self.pages_data: List[Dict] = []
        self.indexable_pages: List[Dict] = []
        
    def load_crawl_data(self, json_path: str) -> bool:
        """Load crawl data from JSON file"""
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                self.pages_data = json.load(f)
            
            # Filter to indexable pages only (v2.0 feature)
            self.indexable_pages = [
                p for p in self.pages_data 
                if p.get('indexable', True) and p.get('page_type') == 'content'
            ]
            
            print(f"📊 Loaded {len(self.pages_data)} total pages")
            print(f"✅ Analyzing {len(self.indexable_pages)} indexable content pages")
            print(f"⏭️  Skipped {len(self.pages_data) - len(self.indexable_pages)} non-indexable pages")
            
            return True
        except Exception as e:
            print(f"Error loading crawl data: {e}")
            return False
    
    def run_audit(self, pages_data: Optional[List[Dict]] = None) -> Dict[str, Any]:
        """Run complete SEO audit on indexable pages only"""
        if pages_data:
            self.pages_data = pages_data
            self.indexable_pages = [
                p for p in pages_data 
                if p.get('indexable', True) and p.get('page_type') == 'content'
            ]
        
        if not self.indexable_pages:
            raise ValueError("No indexable content pages found to audit")
        
        print(f"\n🔍 Starting SEO audit on {len(self.indexable_pages)} indexable pages...")
        
        # Reset state
        self.issues = []
        self.stats = AuditStats()
        self.stats.total_pages = len(self.pages_data)
        self.stats.indexable_pages = len(self.indexable_pages)
        self.stats.content_pages = len([p for p in self.pages_data if p.get('page_type') == 'content'])
        
        # Run all audit rules (only on indexable pages)
        self._audit_meta_tags()
        self._audit_content_quality()
        self._audit_heading_structure()
        self._audit_technical_seo()
        self._audit_internal_linking()
        self._audit_url_structure()
        
        # Calculate priority scores and statistics
        self._calculate_priority_scores()
        self._calculate_statistics()
        self._calculate_seo_score()
        
        return self._generate_report()
    
    # ==================== META TAGS AUDITS ====================
    
    def _audit_meta_tags(self):
        """Audit meta tags on indexable pages only"""
        
        # Missing title tags
        missing_titles = [p for p in self.indexable_pages if not p.get('title')]
        if missing_titles:
            self.issues.append(SEOIssue(
                rule_id="META_001",
                title="Missing Title Tags",
                severity=Severity.CRITICAL,
                category=Category.META_TAGS,
                description=f"{len(missing_titles)} indexable pages are missing title tags",
                impact="Pages without titles won't rank in search results. Title tags are the most important on-page SEO element.",
                affected_pages=[p['url'] for p in missing_titles],
                affected_count=len(missing_titles),
                recommendation="Add unique, descriptive title tags to all indexable pages (50-60 characters optimal)",
                how_to_fix="<title>Primary Keyword - Secondary Keyword | Brand</title>"
            ))
        
        # Short title tags
        short_titles = [p for p in self.indexable_pages if p.get('title') and len(p['title']) < 30]
        if short_titles:
            self.issues.append(SEOIssue(
                rule_id="META_002",
                title="Title Tags Too Short",
                severity=Severity.HIGH,
                category=Category.META_TAGS,
                description=f"{len(short_titles)} indexable pages have title tags shorter than 30 characters",
                impact="Short titles miss opportunities to include keywords and may look incomplete in search results.",
                affected_pages=[f"{p['url']} ({len(p['title'])} chars)" for p in short_titles],
                affected_count=len(short_titles),
                recommendation="Expand titles to 50-60 characters for optimal search visibility",
                how_to_fix="Add relevant keywords and context while keeping titles natural and compelling"
            ))
        
        # Long title tags
        long_titles = [p for p in self.indexable_pages if p.get('title') and len(p['title']) > 60]
        if long_titles:
            self.issues.append(SEOIssue(
                rule_id="META_003",
                title="Title Tags Too Long",
                severity=Severity.MEDIUM,
                category=Category.META_TAGS,
                description=f"{len(long_titles)} indexable pages have title tags longer than 60 characters",
                impact="Long titles get truncated in search results, potentially cutting off important keywords.",
                affected_pages=[f"{p['url']} ({len(p['title'])} chars)" for p in long_titles],
                affected_count=len(long_titles),
                recommendation="Shorten titles to 50-60 characters to prevent truncation",
                how_to_fix="Put most important keywords first, remove filler words"
            ))
        
        # Duplicate title tags (only among indexable pages)
        title_counts = Counter([p['title'] for p in self.indexable_pages if p.get('title')])
        duplicate_titles = {title: count for title, count in title_counts.items() if count > 1}
        if duplicate_titles:
            affected = [p for p in self.indexable_pages if p.get('title') in duplicate_titles]
            self.issues.append(SEOIssue(
                rule_id="META_004",
                title="Duplicate Title Tags",
                severity=Severity.HIGH,
                category=Category.META_TAGS,
                description=f"{len(affected)} indexable pages share duplicate title tags",
                impact="Duplicate titles confuse search engines about which page to rank, causing internal competition.",
                affected_pages=[f"{p['url']} → \"{p['title']}\"" for p in affected[:10]],
                affected_count=len(affected),
                recommendation="Create unique title tags for each page that reflect its specific content",
                how_to_fix="Include page-specific keywords and differentiate similar pages"
            ))
        
        # Missing meta descriptions
        missing_desc = [p for p in self.indexable_pages if not p.get('meta_description')]
        if missing_desc:
            self.issues.append(SEOIssue(
                rule_id="META_005",
                title="Missing Meta Descriptions",
                severity=Severity.HIGH,
                category=Category.META_TAGS,
                description=f"{len(missing_desc)} indexable pages are missing meta descriptions",
                impact="Without meta descriptions, search engines create their own snippets, often poorly representing your content.",
                affected_pages=[p['url'] for p in missing_desc],
                affected_count=len(missing_desc),
                recommendation="Write compelling, unique meta descriptions for all indexable pages (150-160 characters)",
                how_to_fix="<meta name=\"description\" content=\"Clear summary with primary keyword and call-to-action\">"
            ))
        
        # Short meta descriptions
        short_desc = [p for p in self.indexable_pages 
                     if p.get('meta_description') and len(p['meta_description']) < 120]
        if short_desc:
            self.issues.append(SEOIssue(
                rule_id="META_006",
                title="Meta Descriptions Too Short",
                severity=Severity.MEDIUM,
                category=Category.META_TAGS,
                description=f"{len(short_desc)} indexable pages have meta descriptions shorter than 120 characters",
                impact="Short descriptions miss opportunities to entice clicks and may look thin in search results.",
                affected_pages=[f"{p['url']} ({len(p['meta_description'])} chars)" for p in short_desc],
                affected_count=len(short_desc),
                recommendation="Expand descriptions to 150-160 characters for maximum impact",
                how_to_fix="Add more context, benefits, and a clear call-to-action"
            ))
        
        # Duplicate meta descriptions (only among indexable)
        desc_counts = Counter([p['meta_description'] for p in self.indexable_pages 
                              if p.get('meta_description')])
        duplicate_desc = {desc: count for desc, count in desc_counts.items() if count > 1}
        if duplicate_desc:
            affected = [p for p in self.indexable_pages 
                       if p.get('meta_description') in duplicate_desc]
            self.issues.append(SEOIssue(
                rule_id="META_007",
                title="Duplicate Meta Descriptions",
                severity=Severity.MEDIUM,
                category=Category.META_TAGS,
                description=f"{len(affected)} indexable pages share duplicate meta descriptions",
                impact="Duplicate descriptions reduce uniqueness and may lower click-through rates from search results.",
                affected_pages=[p['url'] for p in affected[:10]],
                affected_count=len(affected),
                recommendation="Write unique meta descriptions that accurately reflect each page's content",
                how_to_fix="Highlight what makes each page unique and include relevant keywords naturally"
            ))
    
    # ==================== CONTENT QUALITY AUDITS ====================
    
    def _audit_content_quality(self):
        """Audit content quality using main_content_word_count (v2.0)"""
        
        # Use main_content_word_count instead of word_count
        thin_pages = [p for p in self.indexable_pages 
                     if p.get('main_content_word_count', 0) < 300]
        if thin_pages:
            self.issues.append(SEOIssue(
                rule_id="CONTENT_001",
                title="Thin Content Pages",
                severity=Severity.HIGH,
                category=Category.CONTENT,
                description=f"{len(thin_pages)} indexable pages have less than 300 words of main content",
                impact="Thin content pages rarely rank well. Google favors comprehensive, valuable content.",
                affected_pages=[f"{p['url']} ({p.get('main_content_word_count', 0)} words)" 
                              for p in thin_pages],
                affected_count=len(thin_pages),
                recommendation="Expand main content to at least 300 words, ideally 600-1000+ for competitive topics",
                how_to_fix="Add detailed explanations, examples, FAQs, and relevant supporting information"
            ))
        
        # Very thin content (critical)
        very_thin = [p for p in self.indexable_pages 
                    if p.get('main_content_word_count', 0) < 100]
        if very_thin:
            self.issues.append(SEOIssue(
                rule_id="CONTENT_002",
                title="Extremely Thin Content",
                severity=Severity.CRITICAL,
                category=Category.CONTENT,
                description=f"{len(very_thin)} indexable pages have less than 100 words of main content",
                impact="Pages with under 100 words provide minimal value and may be penalized by Google.",
                affected_pages=[f"{p['url']} ({p.get('main_content_word_count', 0)} words)" 
                              for p in very_thin],
                affected_count=len(very_thin),
                recommendation="Add substantial content (300+ words) or consider consolidating these pages",
                how_to_fix="Create comprehensive standalone content or merge with related pages"
            ))
        
        # High boilerplate ratio
        high_boilerplate = [p for p in self.indexable_pages 
                           if p.get('boilerplate_word_count', 0) > p.get('main_content_word_count', 1)]
        if high_boilerplate:
            self.issues.append(SEOIssue(
                rule_id="CONTENT_003",
                title="High Boilerplate-to-Content Ratio",
                severity=Severity.MEDIUM,
                category=Category.CONTENT,
                description=f"{len(high_boilerplate)} pages have more boilerplate than actual content",
                impact="Pages with excessive navigation/footer content dilute the focus on main content.",
                affected_pages=[f"{p['url']} (Main: {p.get('main_content_word_count', 0)}, "
                              f"Boilerplate: {p.get('boilerplate_word_count', 0)})" 
                              for p in high_boilerplate[:10]],
                affected_count=len(high_boilerplate),
                recommendation="Increase main content or reduce repetitive elements",
                how_to_fix="Add more valuable content to these pages or simplify navigation/footer"
            ))
    
    # ==================== HEADING STRUCTURE AUDITS ====================
    
    def _audit_heading_structure(self):
        """Audit heading structure on indexable pages"""
        
        # Missing H1
        missing_h1 = [p for p in self.indexable_pages if not p.get('h1')]
        if missing_h1:
            self.issues.append(SEOIssue(
                rule_id="STRUCT_001",
                title="Missing H1 Tags",
                severity=Severity.CRITICAL,
                category=Category.STRUCTURE,
                description=f"{len(missing_h1)} indexable pages are missing H1 tags",
                impact="H1 tags are crucial for SEO. They tell search engines what the page is about.",
                affected_pages=[p['url'] for p in missing_h1],
                affected_count=len(missing_h1),
                recommendation="Add a unique, keyword-rich H1 tag to every indexable page",
                how_to_fix="<h1>Primary Topic with Target Keyword</h1>"
            ))
        
        # Short H1 tags
        short_h1 = [p for p in self.indexable_pages 
                   if p.get('h1') and len(str(p['h1'])) < 20]
        if short_h1:
            self.issues.append(SEOIssue(
                rule_id="STRUCT_003",
                title="H1 Tags Too Short",
                severity=Severity.LOW,
                category=Category.STRUCTURE,
                description=f"{len(short_h1)} indexable pages have H1 tags shorter than 20 characters",
                impact="Very short H1s may not adequately describe the page content or include target keywords.",
                affected_pages=[f"{p['url']} → \"{p['h1']}\"" for p in short_h1],
                affected_count=len(short_h1),
                recommendation="Expand H1 tags to 20-70 characters with clear, keyword-rich descriptions",
                how_to_fix="Include primary keyword and clear topic description"
            ))
        
        # Missing H2 tags
        missing_h2 = [p for p in self.indexable_pages 
                     if p.get('main_content_word_count', 0) > 300 and len(p.get('h2', [])) == 0]
        if missing_h2:
            self.issues.append(SEOIssue(
                rule_id="STRUCT_004",
                title="Missing H2 Subheadings",
                severity=Severity.MEDIUM,
                category=Category.STRUCTURE,
                description=f"{len(missing_h2)} content pages lack H2 subheadings",
                impact="Pages without subheadings are harder to scan and may have lower user engagement.",
                affected_pages=[p['url'] for p in missing_h2],
                affected_count=len(missing_h2),
                recommendation="Add H2 subheadings to break up content and improve readability",
                how_to_fix="Structure content with clear sections using H2 tags for main topics"
            ))
        
        # H1-Title mismatch
        h1_title_mismatch = []
        for p in self.indexable_pages:
            if p.get('h1') and p.get('title'):
                h1_clean = re.sub(r'\W+', '', str(p['h1']).lower())
                title_clean = re.sub(r'\W+', '', p['title'].lower())
                h1_words = set(h1_clean.split())
                title_words = set(title_clean.split())
                if len(h1_words & title_words) < 2:
                    h1_title_mismatch.append(p)
        
        if h1_title_mismatch:
            self.issues.append(SEOIssue(
                rule_id="STRUCT_005",
                title="H1 and Title Tag Mismatch",
                severity=Severity.LOW,
                category=Category.STRUCTURE,
                description=f"{len(h1_title_mismatch)} indexable pages have unrelated H1 and title tags",
                impact="Mismatched H1 and titles can create confusion about page topic and dilute keyword focus.",
                affected_pages=[f"{p['url']} → H1: \"{p['h1']}\" | Title: \"{p['title']}\"" 
                              for p in h1_title_mismatch[:5]],
                affected_count=len(h1_title_mismatch),
                recommendation="Align H1 and title tags to reinforce primary keyword and topic",
                how_to_fix="Use similar keywords and phrasing in both H1 and title"
            ))
    
    # ==================== TECHNICAL SEO AUDITS ====================
    
    def _audit_technical_seo(self):
        """Audit technical SEO issues"""
        
        # Canonical mismatches (v2.0 feature)
        canonical_issues = [p for p in self.indexable_pages 
                           if p.get('canonical_mismatch', False)]
        if canonical_issues:
            self.issues.append(SEOIssue(
                rule_id="TECH_002",
                title="Canonical URL Mismatches",
                severity=Severity.CRITICAL,
                category=Category.TECHNICAL,
                description=f"{len(canonical_issues)} indexable pages have canonical URLs pointing elsewhere",
                impact="Wrong canonicals tell Google to index a different page, preventing these pages from ranking.",
                affected_pages=[f"{p['url']} → {p.get('canonical_target', 'unknown')}" 
                              for p in canonical_issues[:10]],
                affected_count=len(canonical_issues),
                recommendation="Set canonical URLs to self-reference unless intentionally consolidating content",
                how_to_fix="<link rel=\"canonical\" href=\"https://domain.com/this-page\" />"
            ))
        
        # Check for non-indexable pages that shouldn't be (informational)
        non_indexable_content = [p for p in self.pages_data 
                                if p.get('page_type') == 'content' and not p.get('indexable')]
        if non_indexable_content:
            reasons = Counter([p.get('indexability_reason') for p in non_indexable_content])
            self.issues.append(SEOIssue(
                rule_id="TECH_004",
                title="Content Pages Not Indexable",
                severity=Severity.INFO,
                category=Category.TECHNICAL,
                description=f"{len(non_indexable_content)} content pages are not indexable",
                impact="These pages won't appear in search results. Verify this is intentional.",
                affected_pages=[f"{p['url']} ({p.get('indexability_reason', 'unknown')})" 
                              for p in non_indexable_content[:10]],
                affected_count=len(non_indexable_content),
                recommendation=f"Review why these pages are non-indexable: {dict(reasons)}",
                how_to_fix="Fix canonical issues, add content, or confirm noindex is intentional"
            ))
    
    # ==================== INTERNAL LINKING AUDITS ====================
    
    def _audit_internal_linking(self):
        """Audit internal linking using filtered links (v2.0)"""
        
        # Use internal_links_filtered instead of internal_links
        no_links = [p for p in self.indexable_pages 
                   if len(p.get('internal_links_filtered', [])) == 0]
        if no_links:
            self.issues.append(SEOIssue(
                rule_id="LINK_001",
                title="Orphaned Pages (No Internal Links)",
                severity=Severity.HIGH,
                category=Category.LINKS,
                description=f"{len(no_links)} indexable pages have no outgoing internal links",
                impact="Pages without internal links don't pass PageRank and create dead-ends.",
                affected_pages=[p['url'] for p in no_links],
                affected_count=len(no_links),
                recommendation="Add contextual internal links to related pages",
                how_to_fix="Link to 3-5 related pages using descriptive anchor text"
            ))
        
        # Weak internal linking
        few_links = [p for p in self.indexable_pages 
                    if 0 < len(p.get('internal_links_filtered', [])) < 3 
                    and p.get('main_content_word_count', 0) > 300]
        if few_links:
            self.issues.append(SEOIssue(
                rule_id="LINK_002",
                title="Weak Internal Linking",
                severity=Severity.MEDIUM,
                category=Category.LINKS,
                description=f"{len(few_links)} content pages have fewer than 3 internal links",
                impact="Limited internal linking reduces PageRank distribution.",
                affected_pages=[f"{p['url']} ({len(p.get('internal_links_filtered', []))} links)" 
                              for p in few_links],
                affected_count=len(few_links),
                recommendation="Add more internal links to strengthen site architecture",
                how_to_fix="Aim for 3-8 contextual internal links per content page"
            ))
    
    # ==================== URL STRUCTURE AUDITS ====================
    
    def _audit_url_structure(self):
        """Audit URL structure"""
        
        # Long URLs
        long_urls = [p for p in self.indexable_pages 
                    if len(p.get('normalized_url', p.get('url', ''))) > 100]
        if long_urls:
            self.issues.append(SEOIssue(
                rule_id="URL_001",
                title="URLs Too Long",
                severity=Severity.LOW,
                category=Category.TECHNICAL,
                description=f"{len(long_urls)} indexable pages have URLs longer than 100 characters",
                impact="Long URLs are harder to share and may get truncated.",
                affected_pages=[f"{p.get('normalized_url', p['url'])} ({len(p.get('normalized_url', p['url']))} chars)" 
                              for p in long_urls],
                affected_count=len(long_urls),
                recommendation="Keep URLs under 100 characters when possible",
                how_to_fix="Use shorter, keyword-rich URLs"
            ))
        
        # Non-descriptive URLs
        non_descriptive = [p for p in self.indexable_pages 
                          if re.search(r'/(page|item|product)\d+', p.get('url', ''))]
        if non_descriptive:
            self.issues.append(SEOIssue(
                rule_id="URL_003",
                title="Non-Descriptive URLs",
                severity=Severity.LOW,
                category=Category.TECHNICAL,
                description=f"{len(non_descriptive)} pages have non-descriptive URLs with IDs",
                impact="URLs with IDs are less meaningful than keyword-rich URLs.",
                affected_pages=[p['url'] for p in non_descriptive],
                affected_count=len(non_descriptive),
                recommendation="Use descriptive, keyword-rich URLs",
                how_to_fix="Use /blog/seo-tips instead of /blog/post123"
            ))
    
    # ==================== SCORING & REPORTING ====================
    
    def _calculate_priority_scores(self):
        """Calculate priority scores for issues"""
        severity_weights = {
            Severity.CRITICAL: 100,
            Severity.HIGH: 75,
            Severity.MEDIUM: 50,
            Severity.LOW: 25,
            Severity.INFO: 10
        }
        
        for issue in self.issues:
            base_score = severity_weights[issue.severity]
            
            # Multiply by percentage of affected indexable pages
            if self.stats.indexable_pages > 0:
                impact_multiplier = issue.affected_count / self.stats.indexable_pages
                issue.priority_score = int(base_score * (1 + impact_multiplier))
            else:
                issue.priority_score = base_score
    
    def _calculate_statistics(self):
        """Calculate audit statistics"""
        for issue in self.issues:
            if issue.severity == Severity.CRITICAL:
                self.stats.critical_issues += 1
            elif issue.severity == Severity.HIGH:
                self.stats.high_issues += 1
            elif issue.severity == Severity.MEDIUM:
                self.stats.medium_issues += 1
            elif issue.severity == Severity.LOW:
                self.stats.low_issues += 1
            elif issue.severity == Severity.INFO:
                self.stats.info_issues += 1
        
        self.stats.total_issues = len(self.issues)
        
        # Calculate pages with issues (from indexable pages only)
        affected_urls = set()
        for issue in self.issues:
            if issue.severity != Severity.INFO:
                affected_urls.update(issue.affected_pages[:100])
        self.stats.pages_with_issues = len(affected_urls)
        
        # Average main content word count (v2.0)
        if self.indexable_pages:
            word_counts = [p.get('main_content_word_count', 0) for p in self.indexable_pages]
            self.stats.avg_word_count = sum(word_counts) / len(word_counts) if word_counts else 0
    
    def _calculate_seo_score(self):
        """Calculate overall SEO health score (0-100)"""
        score = 100
        
        score -= self.stats.critical_issues * 10
        score -= self.stats.high_issues * 5
        score -= self.stats.medium_issues * 2
        score -= self.stats.low_issues * 0.5
        
        self.stats.seo_score = max(0, int(score))
    
    def _generate_report(self) -> Dict[str, Any]:
        """Generate complete audit report"""
        sorted_issues = sorted(self.issues, key=lambda x: x.priority_score, reverse=True)
        
        return {
            "audit_metadata": {
                "generated_at": datetime.utcnow().isoformat(),
                "crawler_version": "2.0",
                "total_pages_crawled": self.stats.total_pages,
                "indexable_pages_analyzed": self.stats.indexable_pages,
                "content_pages": self.stats.content_pages,
                "seo_score": self.stats.seo_score,
                "score_grade": self._get_score_grade(self.stats.seo_score)
            },
            "summary": {
                "total_issues": self.stats.total_issues,
                "critical_issues": self.stats.critical_issues,
                "high_issues": self.stats.high_issues,
                "medium_issues": self.stats.medium_issues,
                "low_issues": self.stats.low_issues,
                "info_issues": self.stats.info_issues,
                "pages_with_issues": self.stats.pages_with_issues,
                "avg_main_content_word_count": round(self.stats.avg_word_count, 1)
            },
            "issues_by_severity": {
                "critical": [i.to_dict() for i in sorted_issues if i.severity == Severity.CRITICAL],
                "high": [i.to_dict() for i in sorted_issues if i.severity == Severity.HIGH],
                "medium": [i.to_dict() for i in sorted_issues if i.severity == Severity.MEDIUM],
                "low": [i.to_dict() for i in sorted_issues if i.severity == Severity.LOW],
                "info": [i.to_dict() for i in sorted_issues if i.severity == Severity.INFO]
            },
            "issues_by_category": self._group_by_category(sorted_issues),
            "top_priorities": [i.to_dict() for i in sorted_issues[:10]],
            "quick_wins": self._get_quick_wins(sorted_issues)
        }
    
    def _get_score_grade(self, score: int) -> str:
        """Convert score to letter grade"""
        if score >= 90:
            return "A - Excellent"
        elif score >= 80:
            return "B - Good"
        elif score >= 70:
            return "C - Fair"
        elif score >= 60:
            return "D - Poor"
        else:
            return "F - Critical Issues"
    
    def _group_by_category(self, issues: List[SEOIssue]) -> Dict[str, List[Dict]]:
        """Group issues by category"""
        by_category = defaultdict(list)
        for issue in issues:
            by_category[issue.category.value].append(issue.to_dict())
        return dict(by_category)
    
    def _get_quick_wins(self, issues: List[SEOIssue]) -> List[Dict]:
        """Identify quick wins - high impact, easy to fix"""
        quick_wins = []
        
        quick_win_rules = {
            'META_005', 'META_006', 'STRUCT_001', 'TECH_002',
            'LINK_001', 'META_002', 'STRUCT_004'
        }
        
        for issue in issues:
            if issue.rule_id in quick_win_rules and issue.severity in [Severity.HIGH, Severity.CRITICAL]:
                quick_wins.append(issue.to_dict())
        
        return quick_wins[:5]
    
    def save_report(self, output_path: str):
        """Save audit report to JSON file"""
        report = self._generate_report()
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        print(f"✅ Audit report saved to: {output_path}")
        return output_path
    
    def print_summary(self):
        """Print human-readable summary"""
        print("\n" + "="*70)
        print("📊 SEO AUDIT SUMMARY (v2.0 - Indexable Pages Only)")
        print("="*70)
        print(f"\n🎯 SEO Health Score: {self.stats.seo_score}/100 - {self._get_score_grade(self.stats.seo_score)}")
        print(f"📄 Total Pages Crawled: {self.stats.total_pages}")
        print(f"✅ Indexable Pages Analyzed: {self.stats.indexable_pages}")
        print(f"📝 Content Pages: {self.stats.content_pages}")
        print(f"⏭️  Non-indexable Pages Skipped: {self.stats.total_pages - self.stats.indexable_pages}")
        print(f"\n⚠️  Total Issues Found: {self.stats.total_issues}")
        print(f"\n🔴 Critical Issues: {self.stats.critical_issues}")
        print(f"🟠 High Priority: {self.stats.high_issues}")
        print(f"🟡 Medium Priority: {self.stats.medium_issues}")
        print(f"🟢 Low Priority: {self.stats.low_issues}")
        print(f"ℹ️  Informational: {self.stats.info_issues}")
        
        if self.stats.critical_issues > 0:
            print("\n⚠️  CRITICAL ISSUES REQUIRE IMMEDIATE ATTENTION!")
        
        print(f"\n📊 Avg Main Content: {round(self.stats.avg_word_count, 1)} words")
        print("\n" + "="*70 + "\n")


# ==================== USAGE EXAMPLES ====================

def audit_from_file(crawl_json_path: str, output_dir: str = "audit_reports") -> str:
    """
    Run audit from crawl JSON file (v2.0 compatible)
    
    Args:
        crawl_json_path: Path to pages JSON from crawler v2.0
        output_dir: Directory to save audit report
    
    Returns:
        Path to generated audit report
    """
    engine = SEOAuditEngine()
    
    if not engine.load_crawl_data(crawl_json_path):
        raise ValueError(f"Failed to load crawl data from {crawl_json_path}")
    
    report = engine.run_audit()
    engine.print_summary()
    
    Path(output_dir).mkdir(exist_ok=True)
    
    # Extract domain from first indexable page
    if engine.indexable_pages:
        domain = urlparse(engine.indexable_pages[0]['url']).netloc.replace('.', '_')
    else:
        domain = "site"
    
    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    output_path = f"{output_dir}/audit_{domain}_{timestamp}.json"
    
    engine.save_report(output_path)
    
    return output_path


def audit_from_data(pages_data: List[Dict], output_path: str = None) -> Dict:
    """
    Run audit from pages data directly (v2.0 compatible)
    
    Args:
        pages_data: List of page dictionaries from crawler v2.0
        output_path: Optional path to save report
    
    Returns:
        Audit report dictionary
    """
    engine = SEOAuditEngine()
    report = engine.run_audit(pages_data)
    engine.print_summary()
    
    if output_path:
        engine.save_report(output_path)
    
    return report


# Example usage
if __name__ == "__main__":
    # Example: Audit from v2.0 crawler JSON file
    report_path = audit_from_file(
        crawl_json_path="crawler_output/brutt_in_20251216_053549_pages.json",
        output_dir="audit_reports"
    )
    print(f"\n🎉 Audit complete! Report saved to: {report_path}")