#!/usr/bin/env python3
"""
Execution Plan Generator

Converts SEO fix recommendations into an actionable roadmap with owner assignment,
effort estimation, and sprint planning.

Answers: "What do we fix first, who should fix it, and how long will it take?"

This module is a PLANNER, not an analyzer. It never re-calculates or infers SEO logic.
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Tuple
from collections import defaultdict


# Owner assignment rules
OWNER_RULES = {
    'CANONICAL': 'Engineering',
    'REDIRECT': 'Engineering',
    'NOINDEX': 'Engineering',
    'ROBOTS': 'Engineering',
    'CRAWL': 'Engineering',
    'THIN': 'Content',
    'WEAK': 'Content',
    'CONTENT': 'Content',
    'ORPHAN': 'SEO',
    'AUTHORITY': 'SEO',
    'DEAD': 'SEO',
    'POOR': 'SEO',
    'STRUCTURE': 'SEO'
}

# Time buckets (minutes)
TIME_BUCKETS = {
    'LOW': 30,      # 30 minutes
    'MEDIUM': 120,  # 2 hours
    'HIGH': 480     # 8 hours (1 day)
}


class ExecutionPlanGenerator:
    """
    Execution Plan Generator - Converts fix recommendations into actionable roadmap.
    
    Consumes outputs from:
    - SEO Fix Recommendation Engine (required)
    - Page Priority Engine (optional)
    - Canonical Clusters (optional)
    - Indexability Analyzer (optional)
    """
    
    def __init__(self, base_path: str):
        """
        Initialize Execution Plan Generator.
        
        Args:
            base_path: Base path to input files
        """
        self.base_path = base_path
        self.base_name = Path(base_path).stem
        self.output_dir = Path(base_path).parent
        
        # Data storage
        self.fix_recommendations = []
        self.fix_summary = {}
        self.priority_data = {}
        
        # Results
        self.tasks = []
        self.task_counter = 0
    
    def load_inputs(self):
        """Load all required and optional input files."""
        print("Loading input files...\n")
        
        # Required: seo_fix_recommendations.json
        recommendations_file = f"{self.base_path}_seo_fix_recommendations.json"
        print(f"  ✓ Loading {Path(recommendations_file).name} (REQUIRED)...")
        try:
            with open(recommendations_file, 'r', encoding='utf-8') as f:
                self.fix_recommendations = json.load(f)
            print(f"    Loaded {len(self.fix_recommendations)} fix recommendations")
        except FileNotFoundError:
            print(f"    ✗ Error: {Path(recommendations_file).name} not found")
            print(f"    Please run seo_fix_recommendation_engine.py first")
            raise
        
        # Required: seo_fix_summary.json
        summary_file = f"{self.base_path}_seo_fix_summary.json"
        print(f"  ✓ Loading {Path(summary_file).name} (REQUIRED)...")
        try:
            with open(summary_file, 'r', encoding='utf-8') as f:
                self.fix_summary = json.load(f)
            print(f"    Loaded summary: {self.fix_summary.get('total_fixes', 0)} total fixes")
        except FileNotFoundError:
            print(f"    ✗ Error: {Path(summary_file).name} not found")
            print(f"    Please run seo_fix_recommendation_engine.py first")
            raise
        
        # Optional: page_priority_scores.json
        priority_file = f"{self.base_path}_page_priority_scores.json"
        if os.path.exists(priority_file):
            print(f"  ✓ Loading {Path(priority_file).name} (OPTIONAL)...")
            with open(priority_file, 'r', encoding='utf-8') as f:
                priority_pages = json.load(f)
                self.priority_data = {p['url']: p for p in priority_pages}
            print(f"    Loaded {len(self.priority_data)} priority records")
        else:
            print(f"  ⚠ {Path(priority_file).name} not found (optional, skipping)")
        
        print("\nData loading complete.\n")
    
    def normalize_tasks(self):
        """Group fixes per page into tasks."""
        print("Normalizing tasks...\n")
        
        task_map = {}
        
        for rec in self.fix_recommendations:
            url = rec['url']
            
            # Skip pages with no fixes or skip_reason
            if 'skip_reason' in rec or not rec.get('fix_plan'):
                continue
            
            # Create task if not exists
            if url not in task_map:
                self.task_counter += 1
                task_map[url] = {
                    'task_id': f"TASK_{self.task_counter:03d}",
                    'url': url,
                    'priority': rec.get('priority_tier', 'LOW'),
                    'confidence': rec.get('confidence', 0.5),
                    'actions': []
                }
            
            # Add all fixes as actions
            for fix in rec.get('fix_plan', []):
                task_map[url]['actions'].append({
                    'type': fix.get('issue_code', 'UNKNOWN'),
                    'description': fix.get('fix', ''),
                    'effort': fix.get('effort', 'MEDIUM'),
                    'impact': fix.get('impact', 'LOW'),
                    'fix_score': fix.get('fix_score', 0.5),
                    'source_module': fix.get('source', 'unknown')
                })
        
        self.tasks = list(task_map.values())
        print(f"Created {len(self.tasks)} tasks from {len(self.fix_recommendations)} pages\n")
    
    def assign_owner(self, actions: List[Dict]) -> str:
        """
        Determine primary owner for a task.
        
        Args:
            actions: List of actions
            
        Returns:
            Owner name
        """
        # Count actions by owner
        owner_counts = defaultdict(int)
        
        for action in actions:
            issue_type = action['type']
            # Match first word of issue code to owner rule
            for keyword, owner in OWNER_RULES.items():
                if keyword in issue_type:
                    owner_counts[owner] += 1
                    break
            else:
                # Default to SEO if no match
                owner_counts['SEO'] += 1
        
        # Return primary owner (most actions)
        if owner_counts:
            return max(owner_counts.items(), key=lambda x: x[1])[0]
        return 'SEO'
    
    def calculate_task_effort(self, actions: List[Dict]) -> Tuple[str, str]:
        """
        Calculate total effort for a task.
        
        Args:
            actions: List of actions
            
        Returns:
            Tuple of (effort_level, time_estimate)
        """
        # Sum all action efforts
        total_minutes = sum(TIME_BUCKETS.get(a['effort'], 60) for a in actions)
        
        # Bucket the total
        if total_minutes < 60:
            return 'LOW', f"{total_minutes}m"
        elif total_minutes < 180:
            hours = total_minutes // 60
            minutes = total_minutes % 60
            if minutes > 0:
                return 'MEDIUM', f"{hours}h {minutes}m"
            return 'MEDIUM', f"{hours}h"
        else:
            hours = total_minutes / 60
            return 'HIGH', f"{hours:.1f}h"
    
    def calculate_execution_score(self, task: Dict) -> float:
        """
        Calculate execution priority score.
        
        Formula: priority_score × avg_fix_score × confidence
        
        Args:
            task: Task dict
            
        Returns:
            Execution score
        """
        # Get page priority score
        priority_data = self.priority_data.get(task['url'], {})
        priority_score = priority_data.get('priority_score', 0.5)
        
        # Get average fix score
        fix_scores = [a.get('fix_score', 0.5) for a in task['actions']]
        avg_fix_score = sum(fix_scores) / len(fix_scores) if fix_scores else 0.5
        
        # Get confidence
        confidence = task.get('confidence', 0.5)
        
        # Formula
        execution_score = priority_score * avg_fix_score * confidence
        
        return round(execution_score, 3)
    
    def assign_sprint(self, task: Dict) -> str:
        """
        Assign task to a sprint.
        
        Args:
            task: Task dict
            
        Returns:
            Sprint name
        """
        priority = task['priority']
        effort = task['effort']
        confidence = task.get('confidence', 0.5)
        
        # Sprint 1: Critical + quick wins
        if priority == 'CRITICAL' and effort in ['LOW', 'MEDIUM']:
            return 'Sprint 1'
        
        # Sprint 1: High priority + low effort
        if priority == 'HIGH' and effort == 'LOW':
            return 'Sprint 1'
        
        # Sprint 2: High impact + medium effort
        if priority in ['HIGH', 'MEDIUM'] and effort == 'MEDIUM':
            return 'Sprint 2'
        
        # Sprint 2: Medium priority + low effort
        if priority == 'MEDIUM' and effort == 'LOW':
            return 'Sprint 2'
        
        # Backlog: Everything else
        return 'Backlog'
    
    def calculate_expected_impact(self, task: Dict) -> str:
        """OPTIONAL 3: Calculate expected ROI/impact label.
        
        Args:
            task: Task dict
            
        Returns:
            Impact label (HIGH/MEDIUM/LOW)
        """
        # Based on priority and execution score
        priority = task.get('priority', 'LOW')
        execution_score = task.get('execution_score', 0)
        
        if priority == 'CRITICAL' or execution_score > 0.7:
            return 'HIGH'
        elif priority == 'HIGH' or execution_score > 0.4:
            return 'MEDIUM'
        else:
            return 'LOW'
    
    def detect_dependencies(self, task: Dict, all_tasks: List[Dict]) -> List[str]:
        """OPTIONAL 1: Detect task dependencies.
        
        Args:
            task: Current task
            all_tasks: All tasks
            
        Returns:
            List of task IDs this task depends on
        """
        dependencies = []
        
        # Rule: Content expansion depends on canonical/redirect fixes
        has_content_fix = any('CONTENT' in a['type'] or 'THIN' in a['type'] for a in task['actions'])
        
        if has_content_fix:
            # Find tasks on same URL with canonical/redirect fixes
            for other_task in all_tasks:
                if other_task['url'] == task['url'] and other_task['task_id'] != task['task_id']:
                    has_canonical_fix = any('CANONICAL' in a['type'] or 'REDIRECT' in a['type'] for a in other_task['actions'])
                    if has_canonical_fix:
                        dependencies.append(other_task['task_id'])
        
        return dependencies
    
    def generate_expected_outcome(self, actions: List[Dict]) -> str:
        """
        Generate expected outcome description.
        
        Args:
            actions: List of actions
            
        Returns:
            Outcome description
        """
        # Categorize actions
        categories = set()
        for action in actions:
            issue_type = action['type']
            if 'CANONICAL' in issue_type or 'REDIRECT' in issue_type:
                categories.add('canonical consolidation')
            elif 'CONTENT' in issue_type or 'THIN' in issue_type:
                categories.add('content improvement')
            elif 'LINK' in issue_type or 'ORPHAN' in issue_type or 'AUTHORITY' in issue_type:
                categories.add('internal linking')
            elif 'INDEX' in issue_type or 'ROBOTS' in issue_type:
                categories.add('indexability')
        
        if not categories:
            return "SEO improvements"
        
        return " & ".join(sorted(categories))
    
    def process_tasks(self):
        """Process all tasks: assign owners, calculate efforts, scores, sprints."""
        print("Processing tasks...\n")
        
        for task in self.tasks:
            # Assign owner
            task['owner'] = self.assign_owner(task['actions'])
            
            # Calculate effort
            task['effort'], task['estimated_time'] = self.calculate_task_effort(task['actions'])
            
            # Calculate execution score
            task['execution_score'] = self.calculate_execution_score(task)
            
            # OPTIONAL 3: Calculate expected impact
            task['expected_impact'] = self.calculate_expected_impact(task)
            
            # Assign sprint
            task['sprint'] = self.assign_sprint(task)
            
            # Generate expected outcome
            task['expected_outcome'] = self.generate_expected_outcome(task['actions'])
        
        # OPTIONAL 1: Detect dependencies (after all tasks processed)
        for task in self.tasks:
            task['depends_on'] = self.detect_dependencies(task, self.tasks)
        
        # Sort by execution score (highest first)
        self.tasks.sort(key=lambda x: x.get('execution_score', 0), reverse=True)
        
        print(f"Processed {len(self.tasks)} tasks\n")
    
    def validate_plan(self) -> List[str]:
        """
        Validate execution plan.
        
        Returns:
            List of validation errors
        """
        errors = []
        
        # Check every task has owner
        for task in self.tasks:
            if not task.get('owner'):
                errors.append(f"Task {task['task_id']} missing owner")
            
            if not task.get('effort'):
                errors.append(f"Task {task['task_id']} missing effort")
        
        # Check sprint distribution
        sprint_efforts = defaultdict(lambda: {'LOW': 0, 'MEDIUM': 0, 'HIGH': 0})
        for task in self.tasks:
            sprint = task.get('sprint', 'Backlog')
            effort = task.get('effort', 'MEDIUM')
            sprint_efforts[sprint][effort] += 1
        
        for sprint, efforts in sprint_efforts.items():
            total = sum(efforts.values())
            if total > 0:
                high_pct = efforts['HIGH'] / total
                if high_pct > 0.4:
                    errors.append(f"{sprint} has {high_pct:.0%} HIGH effort (>40% limit)")
        
        # Check critical issues not in backlog
        for task in self.tasks:
            if task.get('priority') == 'CRITICAL' and task.get('sprint') == 'Backlog':
                errors.append(f"CRITICAL task {task['task_id']} in Backlog")
        
        return errors
    
    def generate_outputs(self):
        """Generate all output files."""
        print("Generating execution plan outputs...\n")
        
        # Validate first
        errors = self.validate_plan()
        if errors:
            print("⚠ Validation warnings:")
            for error in errors:
                print(f"  - {error}")
            print()
        
        # 1. execution_plan.json
        plan_file = self.output_dir / f"{self.base_name}_execution_plan.json"
        plan_data = {"tasks": self.tasks}
        with open(plan_file, 'w', encoding='utf-8') as f:
            json.dump(plan_data, f, indent=2, ensure_ascii=False)
        print(f"  ✓ {plan_file.name}")
        
        # 2. execution_plan_summary.json
        summary = self.generate_summary()
        summary_file = self.output_dir / f"{self.base_name}_execution_plan_summary.json"
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        print(f"  ✓ {summary_file.name}")
        
        # 3. execution_plan_sprints.json
        sprints = self.generate_sprints()
        sprints_file = self.output_dir / f"{self.base_name}_execution_plan_sprints.json"
        with open(sprints_file, 'w', encoding='utf-8') as f:
            json.dump(sprints, f, indent=2, ensure_ascii=False)
        print(f"  ✓ {sprints_file.name}")
        
        # Print summary
        print("\n" + "=" * 70)
        print("📋 EXECUTION PLAN GENERATOR COMPLETE")
        print("=" * 70)
        print(f"\n  Total Tasks: {summary['total_tasks']}")
        print(f"\n  By Owner:")
        for owner, count in summary['by_owner'].items():
            print(f"    {owner}: {count} tasks")
        
        print(f"\n  By Sprint:")
        for sprint, count in summary['by_sprint'].items():
            print(f"    {sprint}: {count} tasks")
        
        print(f"\n  Estimated Time:")
        for owner, time in summary['estimated_total_time'].items():
            print(f"    {owner}: {time}")
        
        print("\n" + "=" * 70 + "\n")
    
    def generate_summary(self) -> Dict:
        """Generate execution plan summary."""
        by_owner = defaultdict(int)
        by_sprint = defaultdict(int)
        time_by_owner = defaultdict(int)  # in minutes
        
        for task in self.tasks:
            owner = task.get('owner', 'Unknown')
            sprint = task.get('sprint', 'Backlog')
            
            by_owner[owner] += 1
            by_sprint[sprint] += 1
            
            # Parse time estimate
            time_str = task.get('estimated_time', '0m')
            minutes = 0
            if 'h' in time_str:
                parts = time_str.split('h')
                minutes += float(parts[0]) * 60
                if len(parts) > 1 and 'm' in parts[1]:
                    minutes += int(parts[1].replace('m', '').strip())
            elif 'm' in time_str:
                minutes = int(time_str.replace('m', ''))
            
            time_by_owner[owner] += minutes
        
        # Convert minutes to hours
        estimated_time = {}
        for owner, minutes in time_by_owner.items():
            hours = minutes / 60
            estimated_time[owner] = f"{hours:.1f}h"
        
        return {
            "total_tasks": len(self.tasks),
            "by_owner": dict(sorted(by_owner.items(), key=lambda x: x[1], reverse=True)),
            "by_sprint": dict(by_sprint),
            "estimated_total_time": estimated_time
        }
    
    def generate_sprints(self) -> Dict:
        """OPTIONAL 2: Generate sprint-based task list with themes."""
        sprint_data = {}
        sprint_tasks = defaultdict(list)
        
        # Group tasks by sprint
        for task in self.tasks:
            sprint = task.get('sprint', 'Backlog')
            
            # Create concise task description
            action_types = set(a['type'] for a in task['actions'])
            description = f"{task['task_id']}: {', '.join(sorted(action_types)[:2])}"
            if len(action_types) > 2:
                description += f" (+{len(action_types) - 2} more)"
            
            sprint_tasks[sprint].append(description)
        
        # OPTIONAL 2: Determine sprint themes
        for sprint, tasks in sprint_tasks.items():
            # Analyze task types to determine theme
            all_actions = []
            for task in self.tasks:
                if task.get('sprint') == sprint:
                    all_actions.extend([a['type'] for a in task['actions']])
            
            # Count action types
            action_counts = defaultdict(int)
            for action_type in all_actions:
                if 'CANONICAL' in action_type or 'REDIRECT' in action_type:
                    action_counts['Canonical Cleanup'] += 1
                elif 'CONTENT' in action_type or 'THIN' in action_type:
                    action_counts['Content Enhancement'] += 1
                elif 'LINK' in action_type or 'ORPHAN' in action_type:
                    action_counts['Internal Linking'] += 1
                elif 'INDEX' in action_type or 'ROBOTS' in action_type:
                    action_counts['Indexability Fixes'] += 1
            
            # Determine primary theme
            if action_counts:
                theme = max(action_counts.items(), key=lambda x: x[1])[0]
            else:
                theme = 'General SEO Improvements'
            
            sprint_data[sprint] = {
                'theme': theme,
                'tasks': tasks
            }
        
        return sprint_data
    
    def run(self):
        """Run the complete execution plan generator."""
        self.load_inputs()
        self.normalize_tasks()
        self.process_tasks()
        self.generate_outputs()


def main():
    """Main entry point."""
    print("=" * 70)
    print("📋 EXECUTION PLAN GENERATOR")
    print("=" * 70)
    print()
    
    # Get input path
    print("Enter path to your pages JSON file:")
    print("Example: crawler_output/developer_mozilla_org_20251220_054821_pages.json")
    print()
    pages_path = input("Pages JSON path: ").strip()
    
    if not pages_path:
        print("Error: No path provided")
        return
    
    # Remove _pages.json suffix if present
    if pages_path.endswith('_pages.json'):
        base_path = pages_path[:-len('_pages.json')]
    else:
        base_path = pages_path
    
    # Check if file exists
    if not os.path.exists(f"{base_path}_pages.json"):
        print(f"Error: File not found: {base_path}_pages.json")
        return
    
    print()
    print("=" * 70)
    print("📋 EXECUTION PLAN GENERATOR")
    print("=" * 70)
    print()
    
    # Run generator
    generator = ExecutionPlanGenerator(base_path)
    generator.run()


if __name__ == "__main__":
    main()
