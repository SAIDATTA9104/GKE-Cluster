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
  # credentials via env GOOGLE_APPLICATION_CREDENTIALS in pipeline
}

provider "google-beta" {
  project = var.project_id
  region  = var.region
}

#########################
# Artifact Registry Repo
#########################
resource "google_artifact_registry_repository" "artifact_repo" {
  provider = google
  location     = var.region
  repository_id = var.artifact_repo_id
  description  = "Repo for container images for cloud run job"
  format       = "DOCKER"
  cleanup_policy {
    prevent_repo_deletion = false
  }
}

#########################
# Service Accounts
#########################

# Service account that will run the Cloud Run Job (container runs as this SA)
resource "google_service_account" "job_sa" {
  account_id   = "${var.project_short}-cloudrun-job-sa"
  display_name = "Cloud Run Job runtime service account"
}

# Service account used by Cloud Scheduler to call the Run Job API
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
        # pass env var or mount secrets as needed
        env {
          name  = "GCP_PROJECT_ID"
          value = var.project_id
        }
        # add more env vars if required
      }

      service_account = google_service_account.job_sa.email

      # optional: task count or cpu/memory
      scaling {
        max_instance_request_concurrency = 1
      }
    }
  }

  # keep deletion protection off in prod you may want true
  deletion_protection = false
}

# Grant the scheduler_invoker_sa permission to invoke/run the job:
resource "google_cloud_run_v2_job_iam_member" "invoker_binding" {
  provider = google
  project  = var.project_id
  location = var.region
  job      = google_cloud_run_v2_job.oci_report_job.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.scheduler_invoker_sa.email}"
}

#########################
# Cloud Scheduler job - trigger the Cloud Run Job daily at 00:00
#########################

# Cloud Scheduler will call the Cloud Run Jobs API endpoint:
# POST https://run.googleapis.com/v1/projects/{project}/locations/{location}/jobs/{job}:run
# We use oauth_token block to attach an OIDC identity (scheduler will mint token).
resource "google_cloud_scheduler_job" "daily_run" {
  name     = "${var.cloudrun_job_name}-daily-trigger"
  description = "Trigger Cloud Run Job daily at 00:00"
  schedule = "0 0 * * *"  # 12:00 AM every day (server local -> scheduler uses project timezone unless timezone specified)
  time_zone = var.time_zone

  http_target {
    uri = "https://run.googleapis.com/v1/projects/${var.project_id}/locations/${var.region}/jobs/${google_cloud_run_v2_job.oci_report_job.name}:run"
    http_method = "POST"
    # Authorization via OIDC token
    oauth_token {
      service_account_email = google_service_account.scheduler_invoker_sa.email
    }

    # Optional: add body json to pass overrides, e.g. to run with args
    body = jsonencode({
      "name" = google_cloud_run_v2_job.oci_report_job.name
    })
  }
}

#########################
# IAM: grant scheduler SA token creator on itself (needed in some org setups)
#########################
resource "google_project_iam_member" "scheduler_token_creator" {
  project = var.project_id
  role    = "roles/iam.serviceAccountTokenCreator"
  member  = "serviceAccount:${google_service_account.scheduler_invoker_sa.email}"
}

#########################
# IAM: minimal perms for job SA to access storage / bigquery if needed (example)
#########################
resource "google_project_iam_member" "job_sa_storage_view" {
  project = var.project_id
  role    = "roles/storage.objectViewer"
  member  = "serviceAccount:${google_service_account.job_sa.email}"
}

resource "google_project_iam_member" "job_sa_logs" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.job_sa.email}"

}


######################
variable "project_id" {
  description = "GCP project id"
  type        = string
}

variable "project_short" {
  description = "short name for project used in SA ids"
  type        = string
  default     = "proj"
}

variable "region" {
  description = "GCP region"
  type        = string
  default     = "asia-south1"
}

variable "time_zone" {
  description = "Timezone for scheduler (eg Asia/Kolkata)"
  type        = string
  default     = "Asia/Kolkata"
}

variable "terraform_state_bucket" {
  description = "GCS bucket name for terraform state"
  type        = string
}

variable "artifact_repo_id" {
  description = "Artifact Registry repository id (docker registry name)"
  type        = string
  default     = "cloudrun-images"
}

variable "cloudrun_job_name" {
  description = "Name for Cloud Run Job"
  type        = string
  default     = "oci-report-downloader-job"
}

variable "container_image" {
  description = "Fully qualified container image (artifact registry) to deploy to Cloud Run Job"
  type        = string
}

# optional extra variables (e.g. secret names, bucket names)

##############

project_id = "my-gcp-project"
project_short = "myproj"
region = "asia-south1"
time_zone = "Asia/Kolkata"
terraform_state_bucket = "my-tf-state-bucket"
artifact_repo_id = "cloudrun-images"
cloudrun_job_name = "oci-report-downloader-job"
container_image = "asia-south1-docker.pkg.dev/my-gcp-project/cloudrun-images/oci-reports:latest"


#################
output "cloud_run_job_name" {
  value = google_cloud_run_v2_job.oci_report_job.name
}

output "cloud_run_job_location" {
  value = google_cloud_run_v2_job.oci_report_job.location
}

output "scheduler_job_name" {
  value = google_cloud_scheduler_job.daily_run.name
}

output "artifact_registry_repo" {
  value = google_artifact_registry_repository.artifact_repo.repository_id
}

