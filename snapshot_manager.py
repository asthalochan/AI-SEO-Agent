#!/usr/bin/env python3
"""
Snapshot Manager

Infrastructure module for saving and loading SEO analysis snapshots.

Purpose: "What exactly did the site look like at this point in time?"

Enables:
- Before/after comparison
- Impact tracking
- Regression detection
- Historical SEO audits
- Trustworthy ROI reporting

This is infrastructure, not analysis. It does NOT analyze, modify, or compute.
"""

import json
import os
import shutil
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime


class SnapshotManager:
    """
    Snapshot Manager - Infrastructure for immutable SEO snapshots.
    
    Responsibilities:
    - Save module outputs as immutable snapshots
    - Enforce snapshot completeness
    - Load snapshots by date
    - Expose snapshot metadata
    """
    
    def __init__(self, snapshots_dir: str = "snapshots"):
        """
        Initialize Snapshot Manager.
        
        Args:
            snapshots_dir: Root directory for all snapshots
        """
        self.snapshots_dir = Path(snapshots_dir)
        self.snapshots_dir.mkdir(exist_ok=True)
    
    def save_snapshot(
        self,
        domain: str,
        snapshot_date: str,
        outputs: Dict[str, str],
        crawl_metadata: Optional[Dict] = None
    ) -> Dict:
        """
        Save a complete snapshot.
        
        Args:
            domain: Domain name (e.g., "developer.mozilla.org")
            snapshot_date: Snapshot date (YYYY-MM-DD)
            outputs: Dict mapping module names to output file paths
            crawl_metadata: Optional crawl metadata
            
        Returns:
            Validation report
        """
        print(f"Saving snapshot for {domain} ({snapshot_date})...\n")
        
        # Create snapshot directory
        snapshot_dir = self.snapshots_dir / domain / snapshot_date
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        
        # Copy all output files
        copied_files = []
        for module_name, file_path in outputs.items():
            if not os.path.exists(file_path):
                print(f"  ⚠ Warning: {module_name} file not found: {file_path}")
                continue
            
            # Determine target filename
            target_name = self._get_target_filename(module_name)
            target_path = snapshot_dir / target_name
            
            # Copy file
            shutil.copy2(file_path, target_path)
            copied_files.append(module_name)
            print(f"  ✓ Copied {module_name}: {target_name}")
        
        # Create metadata
        metadata = self._create_metadata(
            domain=domain,
            snapshot_date=snapshot_date,
            modules_present=copied_files,
            crawl_metadata=crawl_metadata
        )
        
        # Save metadata
        metadata_path = snapshot_dir / "metadata.json"
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
        print(f"  ✓ Created metadata.json")
        
        # Validate snapshot
        validation = self.validate_snapshot(domain, snapshot_date)
        
        print(f"\n✅ Snapshot saved: {snapshot_dir}")
        print(f"   Status: {validation['status']}")
        
        if validation['missing_files']:
            print(f"   Missing: {', '.join(validation['missing_files'])}")
        
        return validation
    
    def _get_target_filename(self, module_name: str) -> str:
        """
        Get standardized filename for module.
        
        Args:
            module_name: Module name
            
        Returns:
            Target filename
        """
        filename_map = {
            'pages': 'pages.json',
            'crawler': 'pages.json',
            'link_graph': 'link_graph.json',
            'canonical_clusters': 'canonical_clusters.json',
            'indexability': 'indexability.json',
            'content_quality': 'content_quality.json',
            'page_priority': 'page_priority.json',
            'seo_fixes': 'seo_fixes.json',
            'execution_plan': 'execution_plan.json',
            'redirect_map': 'redirect_map.json'
        }
        
        return filename_map.get(module_name, f"{module_name}.json")
    
    def _create_metadata(
        self,
        domain: str,
        snapshot_date: str,
        modules_present: List[str],
        crawl_metadata: Optional[Dict] = None
    ) -> Dict:
        """
        Create snapshot metadata.
        
        Args:
            domain: Domain name
            snapshot_date: Snapshot date
            modules_present: List of modules included
            crawl_metadata: Optional crawl metadata
            
        Returns:
            Metadata dict
        """
        metadata = {
            'domain': domain,
            'snapshot_date': snapshot_date,
            'created_at': datetime.now().isoformat(),
            'modules_present': sorted(modules_present),
            'version': '1.0'
        }
        
        # Add crawl metadata if provided
        if crawl_metadata:
            metadata['crawl_started'] = crawl_metadata.get('crawl_started')
            metadata['crawl_completed'] = crawl_metadata.get('crawl_completed')
            metadata['crawl_scope'] = crawl_metadata.get('crawl_scope', {})
        
        return metadata
    
    def validate_snapshot(self, domain: str, snapshot_date: str) -> Dict:
        """
        Validate snapshot completeness.
        
        Args:
            domain: Domain name
            snapshot_date: Snapshot date
            
        Returns:
            Validation report
        """
        snapshot_dir = self.snapshots_dir / domain / snapshot_date
        
        if not snapshot_dir.exists():
            return {
                'snapshot_date': snapshot_date,
                'status': 'NOT_FOUND',
                'missing_files': [],
                'warnings': [f"Snapshot directory not found: {snapshot_dir}"]
            }
        
        # Required files
        required_files = [
            'pages.json',
            'link_graph.json',
            'canonical_clusters.json',
            'indexability.json'
        ]
        
        # Optional files (warnings if missing)
        optional_files = [
            'content_quality.json',
            'page_priority.json',
            'seo_fixes.json',
            'execution_plan.json'
        ]
        
        # Check required files
        missing_files = []
        for filename in required_files:
            if not (snapshot_dir / filename).exists():
                missing_files.append(filename)
        
        # Check optional files
        warnings = []
        for filename in optional_files:
            if not (snapshot_dir / filename).exists():
                warnings.append(f"Optional file missing: {filename}")
        
        # Determine status
        if missing_files:
            status = 'INVALID'
        elif warnings:
            status = 'VALID_WITH_WARNINGS'
        else:
            status = 'VALID'
        
        return {
            'snapshot_date': snapshot_date,
            'status': status,
            'missing_files': missing_files,
            'warnings': warnings
        }
    
    def load_snapshot(self, domain: str, snapshot_date: str) -> Dict:
        """
        Load a complete snapshot.
        
        Args:
            domain: Domain name
            snapshot_date: Snapshot date
            
        Returns:
            Dict with all snapshot data
        """
        snapshot_dir = self.snapshots_dir / domain / snapshot_date
        
        if not snapshot_dir.exists():
            raise FileNotFoundError(f"Snapshot not found: {snapshot_dir}")
        
        print(f"Loading snapshot: {domain} ({snapshot_date})\n")
        
        # Load metadata
        metadata_path = snapshot_dir / "metadata.json"
        if metadata_path.exists():
            with open(metadata_path, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
        else:
            metadata = {}
        
        # Load all available files
        snapshot_data = {
            'metadata': metadata,
            'snapshot_dir': str(snapshot_dir)
        }
        
        # List of possible files
        possible_files = [
            'pages.json',
            'link_graph.json',
            'canonical_clusters.json',
            'indexability.json',
            'content_quality.json',
            'page_priority.json',
            'seo_fixes.json',
            'execution_plan.json',
            'redirect_map.json'
        ]
        
        for filename in possible_files:
            file_path = snapshot_dir / filename
            if file_path.exists():
                module_name = filename.replace('.json', '')
                with open(file_path, 'r', encoding='utf-8') as f:
                    snapshot_data[module_name] = json.load(f)
                print(f"  ✓ Loaded {filename}")
        
        print(f"\n✅ Snapshot loaded: {len(snapshot_data) - 2} modules")
        
        return snapshot_data
    
    def list_snapshots(self, domain: Optional[str] = None) -> List[Dict]:
        """
        List all available snapshots.
        
        Args:
            domain: Optional domain filter
            
        Returns:
            List of snapshot metadata
        """
        snapshots = []
        
        if domain:
            # List snapshots for specific domain
            domain_dir = self.snapshots_dir / domain
            if domain_dir.exists():
                for snapshot_dir in sorted(domain_dir.iterdir()):
                    if snapshot_dir.is_dir():
                        metadata = self._get_snapshot_metadata(domain, snapshot_dir.name)
                        if metadata:
                            snapshots.append(metadata)
        else:
            # List all snapshots across all domains
            for domain_dir in sorted(self.snapshots_dir.iterdir()):
                if domain_dir.is_dir():
                    domain_name = domain_dir.name
                    for snapshot_dir in sorted(domain_dir.iterdir()):
                        if snapshot_dir.is_dir():
                            metadata = self._get_snapshot_metadata(domain_name, snapshot_dir.name)
                            if metadata:
                                snapshots.append(metadata)
        
        return snapshots
    
    def _get_snapshot_metadata(self, domain: str, snapshot_date: str) -> Optional[Dict]:
        """
        Get metadata for a specific snapshot.
        
        Args:
            domain: Domain name
            snapshot_date: Snapshot date
            
        Returns:
            Metadata dict or None
        """
        metadata_path = self.snapshots_dir / domain / snapshot_date / "metadata.json"
        
        if metadata_path.exists():
            with open(metadata_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        
        # Return basic metadata if file doesn't exist
        return {
            'domain': domain,
            'snapshot_date': snapshot_date,
            'modules_present': []
        }
    
    def get_snapshot_path(self, domain: str, snapshot_date: str) -> Path:
        """
        Get path to snapshot directory.
        
        Args:
            domain: Domain name
            snapshot_date: Snapshot date
            
        Returns:
            Path to snapshot directory
        """
        return self.snapshots_dir / domain / snapshot_date


def main():
    """Main entry point for interactive usage."""
    print("=" * 70)
    print("🗂️  SNAPSHOT MANAGER")
    print("=" * 70)
    print()
    print("Commands:")
    print("  1. Save snapshot")
    print("  2. Load snapshot")
    print("  3. List snapshots")
    print("  4. Validate snapshot")
    print()
    
    choice = input("Enter command (1-4): ").strip()
    
    manager = SnapshotManager()
    
    if choice == "1":
        # Save snapshot
        domain = input("Domain: ").strip()
        snapshot_date = input("Snapshot date (YYYY-MM-DD): ").strip()
        
        print("\nEnter output file paths (press Enter to skip):")
        outputs = {}
        
        modules = [
            'pages', 'link_graph', 'canonical_clusters', 'indexability',
            'content_quality', 'page_priority', 'seo_fixes', 'execution_plan'
        ]
        
        for module in modules:
            path = input(f"  {module}: ").strip()
            if path:
                outputs[module] = path
        
        validation = manager.save_snapshot(domain, snapshot_date, outputs)
        print(f"\nValidation: {json.dumps(validation, indent=2)}")
    
    elif choice == "2":
        # Load snapshot
        domain = input("Domain: ").strip()
        snapshot_date = input("Snapshot date (YYYY-MM-DD): ").strip()
        
        snapshot = manager.load_snapshot(domain, snapshot_date)
        print(f"\nLoaded modules: {list(snapshot.keys())}")
    
    elif choice == "3":
        # List snapshots
        domain = input("Domain (or press Enter for all): ").strip() or None
        
        snapshots = manager.list_snapshots(domain)
        print(f"\nFound {len(snapshots)} snapshots:\n")
        
        for snap in snapshots:
            print(f"  {snap['domain']} - {snap['snapshot_date']}")
            print(f"    Modules: {', '.join(snap.get('modules_present', []))}")
            print()
    
    elif choice == "4":
        # Validate snapshot
        domain = input("Domain: ").strip()
        snapshot_date = input("Snapshot date (YYYY-MM-DD): ").strip()
        
        validation = manager.validate_snapshot(domain, snapshot_date)
        print(f"\nValidation: {json.dumps(validation, indent=2)}")


if __name__ == "__main__":
    main()
