#!/usr/bin/env python3
"""
Configuration Loading Script for Azure DevOps Pipeline
Loads configuration from config/config.yml and sets pipeline variables
"""

import yaml
import json
import os
import sys
import argparse
from typing import Dict, Any


def load_config(config_path: str) -> Dict[str, Any]:
    """Load and parse the configuration file"""
    try:
        with open(config_path, 'r') as file:
            config = yaml.safe_load(file)
        return config
    except FileNotFoundError:
        print(f"##vso[task.logissue type=error]Configuration file not found: {config_path}")
        sys.exit(1)
    except yaml.YAMLError as e:
        print(f"##vso[task.logissue type=error]Error parsing YAML configuration: {e}")
        sys.exit(1)


def set_pipeline_variable(name: str, value: Any, is_output: bool = False):
    """Set a pipeline variable in Azure DevOps format"""
    if is_output:
        print(f"##vso[task.setvariable variable={name};isOutput=true]{value}")
    else:
        print(f"##vso[task.setvariable variable={name}]{value}")


def main():
    """Main configuration loading function"""
    parser = argparse.ArgumentParser(description='Load pipeline configuration from YAML file')
    parser.add_argument('--config-path', default='config/config.yml', help='Path to configuration file')
    args = parser.parse_args()
    
    # Determine config file path
    if os.path.isabs(args.config_path):
        config_path = args.config_path
    else:
        build_sources_directory = os.environ.get('BUILD_SOURCESDIRECTORY', '.')
        config_path = os.path.join(build_sources_directory, args.config_path)
    
    print(f"Loading configuration from: {config_path}")
    
    # Check if config file exists
    if not os.path.exists(config_path):
        print(f"##vso[task.logissue type=error]Configuration file not found: {config_path}")
        sys.exit(1)
    
    # Load and parse YAML config
    try:
        config = load_config(config_path)
        print("YAML configuration parsed successfully")
    except Exception as e:
        print(f"##vso[task.logissue type=error]Failed to parse YAML: {e}")
        sys.exit(1)
    
    # Set pipeline variables for folders
    if 'folders' in config:
        folders_json = json.dumps(config['folders'])
        set_pipeline_variable('configFolders', folders_json, is_output=True)
        print(f"Set configFolders: {len(config['folders'])} folders")
        
        # Display folder order for visibility
        ordered_folders = sorted(config['folders'], key=lambda x: x.get('order', 999))
        print("Folder execution order:")
        for folder in ordered_folders:
            order = folder.get('order', 'N/A')
            print(f"  {order}. {folder['name']} - {folder['displayName']}")
    
    # Set pipeline variables for other settings
    if 'pipeline' in config:
        pipeline = config['pipeline']
        
        if 'branches' in pipeline:
            branches_json = json.dumps(pipeline['branches'])
            set_pipeline_variable('configBranches', branches_json, is_output=True)
            print("Set configBranches")
        
        if 'prBranches' in pipeline:
            pr_branches_json = json.dumps(pipeline['prBranches'])
            set_pipeline_variable('configPrBranches', pr_branches_json, is_output=True)
            print("Set configPrBranches")
        
        if 'pool' in pipeline:
            pool = pipeline['pool']
            
            if 'name' in pool:
                set_pipeline_variable('configPoolName', pool['name'], is_output=True)
                print(f"Set configPoolName: {pool['name']}")
            
            if 'agentDemand' in pool:
                set_pipeline_variable('configAgentDemand', pool['agentDemand'], is_output=True)
                print(f"Set configAgentDemand: {pool['agentDemand']}")
        
        if 'python' in pipeline:
            python_config = pipeline['python']
            
            if 'version' in python_config:
                set_pipeline_variable('configPythonVersion', python_config['version'], is_output=True)
                print(f"Set configPythonVersion: {python_config['version']}")
            
            if 'script' in python_config:
                set_pipeline_variable('configPythonScript', python_config['script'], is_output=True)
                print(f"Set configPythonScript: {python_config['script']}")
    
    print(f"Configuration loaded successfully from {config_path}")
    print("All pipeline variables have been set successfully")


if __name__ == "__main__":
    main()
