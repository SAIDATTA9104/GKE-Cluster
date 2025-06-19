# Azure DevOps Pipeline

## Overview

This Azure DevOps pipeline automates selective deployment of modules based on keywords detected in the commit message. It triggers on commits to the `main` and `develop` branches and determines which modules to deploy by parsing the commit message for specific keywords.

If no module keywords are found or if the keyword `all` is present, the pipeline deploys all modules.

---

## Trigger

- Branches:
  - `main`
  - `develop`

---

## Variables

| Variable       | Description                                        | Default Value |
|----------------|--------------------------------------------------|---------------|
| `changedModules` | Comma-separated list of modules detected as changed | `''`          |
| `runAll`       | Flag to indicate if all modules should be deployed | `false`       |

---

## Pipeline Stages

### 1. DetectChanges

- **Purpose:** Parses the commit message to detect which modules have changed.
- **Details:**
  - Converts the commit message to lowercase.
  - Checks for the keyword `all` to trigger deployment of all modules.
  - Detects changes for the following modules based on commit message keywords:
    - `project`
    - `iam`
    - `compute`
    - `database`
  - Sets the pipeline variables `changedModules` or `runAll` accordingly.

### 2. Project

- **Depends on:** DetectChanges
- **Condition:** Runs if `runAll` is `true` or if `project` is in `changedModules`.
- **Job:** Deploys the Project module.

### 3. IAM

- **Depends on:** DetectChanges
- **Condition:** Runs if `runAll` is `true` or if `iam` is in `changedModules`.
- **Job:** Deploys the IAM module.

### 4. Compute

- **Depends on:** DetectChanges
- **Condition:** Runs if `runAll` is `true` or if `compute` is in `changedModules`.
- **Job:** Deploys the Compute module.

### 5. Database

- **Depends on:** DetectChanges
- **Condition:** Runs if `runAll` is `true` or if `database` is in `changedModules`.
- **Job:** Deploys the Database module.

---

## Commit Message Guidelines

Include one or more of the following keywords in your commit message to specify which modules to deploy:

- `all` — Deploy all modules.
- `project` — Deploy the Project module.
- `iam` — Deploy the IAM module.
- `compute` — Deploy the Compute module.
- `database` — Deploy the Database module.

If none of these keywords are present, the pipeline defaults to deploying all modules.

---

## Examples

- `Fix bug in project and iam modules`  
  Deploys **Project** and **IAM** modules only.

- `Update compute configuration`  
  Deploys **Compute** module only.

- `Full system update - all modules`  
  Deploys **all** modules.

---

## Summary

This pipeline optimizes deployment by selectively running module deployments based on commit message content, reducing unnecessary work and speeding up delivery.

---
