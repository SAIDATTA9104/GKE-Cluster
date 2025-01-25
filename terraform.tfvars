project_id          = "my-project-id"
region              = "us-central1"
cluster_name        = "my-gke-cluster"
network_name        = "my-vpc"
subnet_name         = "my-subnet"
pods_range_name     = "pods-range"
services_range_name = "services-range"
nodepool_name       = "primary-pool"
initial_node_count  = 3
min_node_count      = 3
max_node_count      = 10
machine_type        = "e2-standard-4"
disk_size_gb        = 40
disk_type           = "pd-standard"
release_channel     = "REGULAR"

maintenance_start_time = "2024-12-31T00:00:00Z"
maintenance_end_time   = "2024-12-31T04:00:00Z"
maintenance_recurrence = "FREQ=WEEKLY;BYDAY=SA,SU"

node_labels = {
  environment = "production"
  team        = "platform"
}

node_tags = ["gke-node", "private-node"]