resource "google_container_node_pool" "primary_nodes" {
  name       = var.nodepool_name
  cluster    = google_container_cluster.primary.name
  location   = var.region
  node_count = var.initial_node_count
  

  autoscaling {
    min_node_count = var.min_node_count
    max_node_count = var.max_node_count
  }

  management {
    auto_repair  = true
    auto_upgrade = true
  }

  node_config {
    machine_type = var.machine_type
    disk_size_gb = 10
    disk_type    = "pd-balanced"

    oauth_scopes = [
      "https://www.googleapis.com/auth/logging.write",
      "https://www.googleapis.com/auth/monitoring",
      "https://www.googleapis.com/auth/devstorage.read_only"
    ]
  }
}