#!/usr/bin/env python3
"""
Change Detection Script for Azure DevOps Pipeline
Detects changes in specified folders and outputs results for pipeline consumption
"""

import argparse
import json
import os
import subprocess
import sys
from typing import List, Dict, Any


def get_changed_files() -> List[str]:
    """Get list of changed files using git diff"""
    try:
        # Check if this is a PR or direct push
        build_reason = os.environ.get('BUILD_REASON', '')
        
        if build_reason == 'PullRequest':
            # PR trigger - compare with target branch
            target_branch = os.environ.get('SYSTEM_PULLREQUEST_TARGETBRANCH', 'develop')
            print(f"PR detected, comparing with target branch: {target_branch}")
            
            # Get changed files between target branch and current HEAD
            result = subprocess.run(
                ['git', 'diff', '--name-only', f'remotes/origin/{target_branch}...HEAD'],
                capture_output=True, text=True, check=True
            )
        else:
            # Direct push to branch - compare with previous commit
            print("Direct push detected, comparing with previous commit")
            result = subprocess.run(
                ['git', 'diff', '--name-only', 'HEAD~1', 'HEAD'],
                capture_output=True, text=True, check=True
            )
        
        changed_files = result.stdout.strip().split('\n') if result.stdout.strip() else []
        return [f for f in changed_files if f]  # Remove empty strings
        
    except subprocess.CalledProcessError as e:
        print(f"Error getting changed files: {e}")
        return []
    except Exception as e:
        print(f"Unexpected error: {e}")
        return []


def detect_folder_changes(changed_files: List[str], folders: List[Dict[str, Any]]) -> List[str]:
    """Detect which folders have changes"""
    changed_folders = []
    
    for folder in folders:
        folder_name = folder['name']
        folder_path = folder['path'].replace('*', '')  # Remove wildcard for comparison
        
        for file_path in changed_files:
            if file_path.startswith(folder_path):
                if folder_name not in changed_folders:
                    changed_folders.append(folder_name)
                break
    
    return changed_folders


def output_azure_devops_variable(changed_modules: List[str]):
    """Output the changed modules in Azure DevOps format"""
    if not changed_modules:
        print("##vso[task.logissue type=error]No module changes detected.")
        print("##vso[task.complete result=Failed;]")
        sys.exit(1)
    
    # Join modules with comma for pipeline consumption
    modules_string = ','.join(changed_modules)
    print(f"The following modules will be deployed: {modules_string}")
    
    # Set output variable for Azure DevOps pipeline
    print(f"##vso[task.setvariable variable=changedModules;isOutput=true]{modules_string}")


def validate_folder_config(folders: List[Dict[str, Any]]) -> bool:
    """Validate folder configuration structure"""
    required_fields = ['name', 'path', 'displayName']
    
    for folder in folders:
        if not isinstance(folder, dict):
            print(f"Error: Invalid folder configuration - expected dict, got {type(folder)}")
            return False
        
        for field in required_fields:
            if field not in folder:
                print(f"Error: Missing required field '{field}' in folder configuration")
                return False
            
            if not isinstance(folder[field], str):
                print(f"Error: Field '{field}' must be a string in folder configuration")
                return False
    
    return True


def main():
    parser = argparse.ArgumentParser(description='Detect changes in specified folders')
    parser.add_argument('--folders', nargs='+', help='List of folder configurations')
    parser.add_argument('--folders-json', help='JSON string of folder configurations')
    
    args = parser.parse_args()
    
    # Parse folder configurations
    if args.folders_json:
        try:
            folders = json.loads(args.folders_json)
            if not isinstance(folders, list):
                print("Error: folders-json must contain a list of folder configurations")
                sys.exit(1)
        except json.JSONDecodeError as e:
            print(f"Error parsing folders JSON: {e}")
            sys.exit(1)
    elif args.folders:
        # Convert command line arguments to folder structure
        folders = []
        for folder_arg in args.folders:
            if ':' in folder_arg:
                name, path = folder_arg.split(':', 1)
                folders.append({
                    'name': name,
                    'path': path,
                    'displayName': f'{name.title()} Module'
                })
            else:
                folders.append({
                    'name': folder_arg,
                    'path': f'{folder_arg}/*',
                    'displayName': f'{folder_arg.title()} Module'
                })
    else:
        # Default folders if none specified
        folders = [
            {'name': 'project', 'path': 'project/*', 'displayName': 'Project Module'},
            {'name': 'iam', 'path': 'iam/*', 'displayName': 'IAM Module'},
            {'name': 'compute', 'path': 'compute/*', 'displayName': 'Compute Module'},
            {'name': 'network', 'path': 'network/*', 'displayName': 'Network Module'},
            {'name': 'database', 'path': 'database/*', 'displayName': 'Database Module'}
        ]
    
    # Validate folder configuration
    if not validate_folder_config(folders):
        print("Error: Invalid folder configuration")
        sys.exit(1)
    
    print("Folder configurations:")
    for folder in folders:
        print(f"  - {folder['name']}: {folder['path']} -> {folder['displayName']}")
    
    # Get changed files
    changed_files = get_changed_files()
    print(f"\nChanged files ({len(changed_files)}):")
    for file_path in changed_files:
        print(f"  - {file_path}")
    
    # Detect folder changes
    changed_modules = detect_folder_changes(changed_files, folders)
    
    # Output results
    output_azure_devops_variable(changed_modules)


if __name__ == '__main__':
    main()
