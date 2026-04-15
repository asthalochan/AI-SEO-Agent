# AI-SEO-Agent

An AI SEO Agent that tells you exactly what to fix, in what order, and why — using only your site data. 

This repository contains a production-grade Python-based SEO Analysis and Decision-Making System that transforms raw crawl data into actionable roadmaps with measurable impact tracking. 

The system answers three critical business questions:
1. **What's broken?** (Analysis)
2. **What should we fix first?** (Decision)
3. **Did our fixes work?** (Measurement)

## Table of Contents
- [System Architecture](#system-architecture)
- [Key Design Principles](#key-design-principles)
- [Data Flow](#data-flow)
- [Installation](#installation)
- [Usage Guide](#usage-guide)
- [Output Files](#output-files)

## System Architecture

The system is organized into a pipeline of modular Python scripts across 5 phases:

### Phase 1: Data Collection
- **Crawler (`crawler.py`)** - Collects page data (HTML, meta tags, links). 
- **Redirect Resolver (`redirect_resolver.py`)** - Maps redirect chains to final URLs.

### Phase 2: Analysis
- **Canonical Clusters (`canonical_clusters.py`)** - Detects duplicate content and canonical issues.
- **Link Graph (`link_graph.py`)** - Calculates PageRank and authority distribution.
- **Indexability Analyzer (`indexability_analyzer.py`)** - Assesses crawlability and indexing eligibility.
- **Content Quality Analyzer (`content_quality_analyzer.py`)** - Scores content quality (A/B/C/D grades).
- **Page Experience Analyzer (`page_experience_analyzer.py`)** - Analyzes Core Web Vitals and UX signals.

### Phase 3: Decision-Making
- **Page Priority Engine (`page_priority_engine.py`)** - Ranks pages by SEO impact opportunity.
- **SEO Fix Recommendation Engine (`seo_fix_recommendation_engine.py`)** - Converts analysis into actionable fixes.

### Phase 4: Execution
- **Execution Plan Generator (`execution_plan_generator.py`)** - Creates roadmaps with owner assignment and sprint planning.

### Phase 5: Measurement
- **Change Impact Tracker (`change_impact_tracker.py`)** - Measures before/after effectiveness of fixes.

## Key Design Principles

1. **No Re-calculation** - Each module consumes outputs from previous modules in the pipeline. We never re-crawl or re-analyze the same data unnecessarily.
2. **URL Normalization** - Consistent redirect → canonical → normalized URL resolution across all modules.
3. **Separation of Concerns** - Analysis ≠ Decision-making ≠ Planning. Each step has its own designated module.
4. **Production-Ready** - Handles missing data gracefully, validates inputs, and provides clear error messages.

## Data Flow

```text
Crawl → Analyze → Decide → Plan → Execute → Measure
  ↓        ↓         ↓        ↓       ↓        ↓
pages   signals  priorities tasks  sprints  impact
```

## Installation

1. Clone this repository.
2. Ensure you have Python installed.
3. Install dependencies using:
   ```bash
   pip install -r requirements.txt
   ```

## Usage Guide

The system is designed to be run sequentially. Follow this pattern to generate your SEO execution plan:

```bash
# Phase 1. Collect Data
python crawler.py
python redirect_resolver.py

# Phase 2. Analyze
python canonical_clusters.py
python link_graph.py
python indexability_analyzer.py
python content_quality_analyzer.py
python page_experience_analyzer.py

# Phase 3. Decide Priorities and Fixes
python page_priority_engine.py
python seo_fix_recommendation_engine.py

# Phase 4. Generate the Execution Plan
python execution_plan_generator.py

# Phase 5. Measure Impact (after fixes are implemented on the site)
python change_impact_tracker.py
```

## Output Files

Each module generates JSON outputs (usually written to `crawler_output/`) that feed into the next stage:
- `pages.json` - Raw crawl data
- `pages_redirect_map.json` - Redirect mappings
- `pages_canonical_clusters.json` - Canonical groupings
- `pages_link_graph.json` - Authority scores
- `indexability_issues.json` - Crawlability problems
- `content_quality_pages.json` - Quality assessments
- `page_experience_scores.json` - UX and Core Web Vitals assessments
- `page_priority_scores.json` - Impact opportunity rankings
- `seo_fix_recommendations.json` - Actionable fixes
- `execution_plan.json` - Task roadmap
- `change_impact_*.json` - Before/after comparisons (winners, failures, summary)
