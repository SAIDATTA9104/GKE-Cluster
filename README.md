# Module Deployment Pipeline

This Azure DevOps pipeline is designed to selectively deploy infrastructure modules based on changes detected in pull requests or commit messages.

## Pipeline Overview

The pipeline consists of two main phases:
1. **Change Detection**: Determines which modules need to be deployed based on pull requests or commit messages.
2. **Module Deployment**: Executes deployments for the identified modules. Modules are Project, IAM, Compute and Database.

## Supported Modules

- **Project**
- **IAM**
- **Compute**
- **Database**

## Trigger Conditions

The pipeline triggers on:
- Pushes to the branches
- Pull requests targeting the branch

## How to Control Module Execution

### Option 1: Via PR Title or Commit Message
Include one of these keywords in your PR title or commit message:
- `all` - Deploys all modules
- `project` - Deploys only the Project module
- `iam` - Deploys only the IAM module
- `compute` - Deploys only the Compute module
- `database` - Deploys only the Database module

### Option 2: Automatic Detection
If no module is specified in the PR title or commit message, the pipeline will:
1. Check for changed files in module directories
2. If no changes are detected, the pipeline will fail with a message asking you to specify modules

## Pipeline Stages

### 1. DetectChanges Stage
- Determines which modules need deployment
- Checks both PR titles and commit messages for module keywords
- Outputs either `runAll` flag or `changedModules` list

### 2. Module Deployment Stages
Each module stage runs only if:
- The `runAll` flag is true, OR
- The module name appears in the `changedModules` list

Available deployment stages:
- `project`
- `iam`
- `compute`
- `database`

## Example Usage

### Deploy all modules:
PR Title: `[ALL] Major infrastructure update`

### Deploy specific modules:
PR Title: `Update IAM policies and Compute configurations`

### Deploy based on file changes:
PR Title: `Compute module changes` (with changes in `compute/` directory)

## Failure Conditions
The pipeline will fail if:
- No module keywords are detected in PR title/commit message
- No relevant file changes are detected
- The required module name isn't specified




## Notes

- Module names in PR titles/commit messages are case-insensitive
- The pipeline is designed to work with Terraform modules (commented templates are available)
- Uncomment and customize the template sections for your specific deployment needs
