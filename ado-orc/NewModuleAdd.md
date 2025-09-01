# How to Add a New Module to the Pipeline

This guide explains how to add a new module to your Azure DevOps pipeline using the Monika Madam Task configuration approach. We'll use an example module called `bigquery`. 

### 1. Update the Configuration
Edit `config/config.yml` and add your new module under the `modules` list:

```yaml
modules:
  - name: bigquery
    path: bigquery/
  # ...other modules...

order:
  - project
  - iam
  - network
  - compute
  - database
  - bigquery
```

### 2. Create the Module Directory
Create the corresponding folder in your repository:

```bash
mkdir bigquery
```

Add any initial files you need, for example:
```bash
touch bigquery/README.md
```

### 3. Update Pipeline Templates
Add a new stage for your module in the pipeline template (e.g., `templates/base-pipeline.yml` or `templates/module-stage.yml`). Example for `base-pipeline.yml`:

```yaml
- stage: bigquery
  dependsOn: database
  condition: contains(dependencies.DetectChanges.outputs['GetChangedFiles.SetRunFlags.changedModules'], 'bigquery')
  jobs:
  - job: DeployBigQuery
    steps:
    - script: echo "Deploying BigQuery Module"
      displayName: 'Deploy BigQuery Module'
```

### 4. Commit and Push
Commit your changes and push to the repository:

```bash
git add config/config.yml templates/ bigquery/
git commit -m "Add BigQuery module to pipeline"
git push
```

## Example: Adding a BigQuery Module

Suppose you want to add a Google BigQuery integration to your pipeline:

1. Add the module to `config/config.yml`:
    ```yaml
    modules:
      - name: bigquery
        path: bigquery/
    order:
      - ...
      - bigquery
    ```
2. Create the directory:
    ```bash
    mkdir bigquery
    touch bigquery/main.tf
    ```
3. Add a deployment stage in your pipeline template, We consider bigquery to run after database, adjust the order accordingly.

    ```yaml
    - stage: bigquery
      dependsOn: database
      condition: contains(dependencies.DetectChanges.outputs['GetChangedFiles.SetRunFlags.changedModules'], 'bigquery')
      jobs:
      - job: DeployBigQuery
        steps:
        - script: echo "Deploying BigQuery Module"
          displayName: 'Deploy BigQuery Module'
    ```
4. Commit and push your changes.

Your pipeline will now detect changes in the `bigquery` folder and deploy the module in the correct order.

