project_id   = "your-project-id"
region       = "us-central1"
cluster_name = "autopilot-standard-cluster"

network_project_id = "gcp-proj1"
network_name       = "tf-cluster-network"
subnet_name        = "gke-subnet"

master_ipv4_cidr_block = "172.16.0.0/28"

master_authorized_networks = [
  {
    cidr_block   = "10.0.0.0/8"
    display_name = "internal-network"
  }
]

labels = {
  environment = "production"
  managed-by  = "terraform"
}

release_channel = "REGULAR"