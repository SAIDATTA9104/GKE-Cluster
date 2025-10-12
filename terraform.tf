Main.tf

terraform {
  required_version = ">= 1.2"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 4.0"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = ">= 4.0"
    }
  }

  backend "gcs" {
    bucket = var.terraform_state_bucket
    prefix = "terraform/state/cloud-run-job"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

provider "google-beta" {
  project = var.project_id
  region  = var.region
}

#########################
# Artifact Registry Repo
#########################
resource "google_artifact_registry_repository" "artifact_repo" {
  location      = var.region
  repository_id = var.artifact_repo_id
  description   = "Artifact registry for Cloud Run job container images"
  format        = "DOCKER"
}

#########################
# Service Account: Scheduler Invoker
#########################

resource "google_service_account" "scheduler_invoker_sa" {
  account_id   = "${var.project_short}-scheduler-invoker-sa"
  display_name = "Cloud Scheduler invoker service account"
}

#########################
# Cloud Run Job (v2)
#########################

resource "google_cloud_run_v2_job" "oci_report_job" {
  provider = google-beta
  name     = var.cloudrun_job_name
  location = var.region

  template {
    template {
      containers {
        image = var.container_image

        # Pass required environment variables
        env {
          name  = "GCP_PROJECT_ID"
          value = var.project_id
        }
      }

      # 👇 Use the EXISTING service account you already have
      service_account = var.existing_job_sa_email

      scaling {
        max_instance_request_concurrency = 1
      }
    }
  }

  deletion_protection = false
}

#########################
# IAM Binding: allow scheduler to invoke/run the job
#########################

resource "google_cloud_run_v2_job_iam_member" "invoker_binding" {
  project  = var.project_id
  location = var.region
  job      = google_cloud_run_v2_job.oci_report_job.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.scheduler_invoker_sa.email}"
}

#########################
# Cloud Scheduler Job (trigger Cloud Run Job)
#########################

resource "google_cloud_scheduler_job" "daily_trigger" {
  name        = "${var.cloudrun_job_name}-daily-trigger"
  description = "Triggers Cloud Run Job daily at 12:00 AM"
  schedule    = "0 0 * * *" # every day at midnight
  time_zone   = var.time_zone

  http_target {
    uri = "https://run.googleapis.com/v1/projects/${var.project_id}/locations/${var.region}/jobs/${google_cloud_run_v2_job.oci_report_job.name}:run"
    http_method = "POST"

    oauth_token {
      service_account_email = google_service_account.scheduler_invoker_sa.email
    }

    body = jsonencode({
      "name" = google_cloud_run_v2_job.oci_report_job.name
    })
  }
}

#########################
# IAM: permissions for Scheduler Invoker SA
#########################

# Allow the Scheduler SA to mint OIDC tokens
resource "google_project_iam_member" "scheduler_token_creator" {
  project = var.project_id
  role    = "roles/iam.serviceAccountTokenCreator"
  member  = "serviceAccount:${google_service_account.scheduler_invoker_sa.email}"
}

#########################
# IAM: permissions for EXISTING Cloud Run Job SA (abc@abc.gserviceaccount.xyz)
#########################

# Allow the job to write logs
resource "google_project_iam_member" "job_sa_logwriter" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${var.existing_job_sa_email}"
}

# Allow the job to access Secret Manager (for fetching OCI secrets)
resource "google_project_iam_member" "job_sa_secretaccessor" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${var.existing_job_sa_email}"
}

# Allow the job to access GCS (if needed to upload reports)
resource "google_project_iam_member" "job_sa_storageadmin" {
  project = var.project_id
  role    = "roles/storage.objectAdmin"
  member  = "serviceAccount:${var.existing_job_sa_email}"
}

# Optional: Allow job to write to BigQuery (if applicable)
resource "google_project_iam_member" "job_sa_bigquery" {
  project = var.project_id
  role    = "roles/bigquery.dataEditor"
  member  = "serviceAccount:${var.existing_job_sa_email}"
}


===================================
variables.tf

variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region"
  type        = string
  default     = "asia-south1"
}

variable "time_zone" {
  description = "Timezone for scheduler"
  type        = string
  default     = "Asia/Kolkata"
}

variable "terraform_state_bucket" {
  description = "GCS bucket name for Terraform state"
  type        = string
}

variable "artifact_repo_id" {
  description = "Artifact registry repository ID"
  type        = string
  default     = "cloudrun-images"
}

variable "cloudrun_job_name" {
  description = "Cloud Run job name"
  type        = string
  default     = "oci-report-downloader-job"
}

variable "container_image" {
  description = "Full path to container image"
  type        = string
}

variable "project_short" {
  description = "Short project name prefix"
  type        = string
  default     = "proj"
}

variable "existing_job_sa_email" {
  description = "Existing Service Account email for running the Cloud Run job"
  type        = string
}


============
project_id             = "my-gcp-project"
region                 = "asia-south1"
time_zone              = "Asia/Kolkata"
terraform_state_bucket = "my-tf-state-bucket"
artifact_repo_id       = "cloudrun-images"
cloudrun_job_name      = "oci-report-downloader-job"
container_image        = "asia-south1-docker.pkg.dev/my-gcp-project/cloudrun-images/oci-reports:latest"

# Existing Service Account (used to run Cloud Run job)
existing_job_sa_email  = "abc@abc.gserviceaccount.xyz"


==============
output

output "cloud_run_job_name" {
  value = google_cloud_run_v2_job.oci_report_job.name
}

output "cloud_run_job_url" {
  value = "https://console.cloud.google.com/run/jobs/details/${var.region}/${google_cloud_run_v2_job.oci_report_job.name}?project=${var.project_id}"
}

output "scheduler_job_name" {
  value = google_cloud_scheduler_job.daily_trigger.name
}


