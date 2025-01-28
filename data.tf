data "google_compute_network" "shared_vpc" {
  project = var.network_project_id
  name    = var.network_name
}

data "google_compute_subnetwork" "shared_subnet" {
  project = var.network_project_id
  name    = var.subnet_name
  region  = var.region
}
