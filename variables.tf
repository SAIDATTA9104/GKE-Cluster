variable "project_id" {
  description = "The project ID to host the cluster in"
  type        = string
}

variable "region" {
  description = "The region to host the cluster in"
  type        = string
}

variable "cluster_name" {
  description = "The name of the GKE cluster"
  type        = string
}

variable "network_name" {
  description = "The name of the VPC network"
  type        = string
}

variable "subnet_name" {
  description = "The name of the subnet"
  type        = string
}

variable "pods_range_name" {
  description = "The name of the secondary IP range for pods"
  type        = string
}

variable "services_range_name" {
  description = "The name of the secondary IP range for services"
  type        = string
}

variable "release_channel" {
  description = "The release channel of the GKE cluster"
  type        = string
  default     = "REGULAR"
}

variable "maintenance_start_time" {
  description = "Start time for maintenance window"
  type        = string
  default     = "2023-01-01T00:00:00Z"
}

variable "maintenance_end_time" {
  description = "End time for maintenance window"
  type        = string
  default     = "2023-01-01T04:00:00Z"
}

variable "maintenance_recurrence" {
  description = "Frequency of maintenance window"
  type        = string
  default     = "FREQ=WEEKLY;BYDAY=SA,SU"
}

variable "nodepool_name" {
  description = "The name of the node pool"
  type        = string
}

variable "initial_node_count" {
  description = "Initial number of nodes in the node pool"
  type        = number
  default     = 3
}

variable "min_node_count" {
  description = "Minimum number of nodes in the node pool"
  type        = number
  default     = 3
}

variable "max_node_count" {
  description = "Maximum number of nodes in the node pool"
  type        = number
  default     = 10
}

variable "machine_type" {
  description = "The machine type for the nodes"
  type        = string
}

variable "disk_size_gb" {
  description = "Size of the disk attached to each node"
  type        = number
}

variable "disk_type" {
  description = "Type of disk attached to each node"
  type        = string
}

variable "auto_repair" {
  description = "Whether to enable auto repair"
  type        = bool
  default     = true
}

variable "auto_upgrade" {
  description = "Whether to enable auto upgrade"
  type        = bool
  default     = true
}

variable "node_labels" {
  description = "Labels to apply to the nodes"
  type        = map(string)
  default     = {}
}

variable "node_tags" {
  description = "Network tags to apply to the nodes"
  type        = list(string)
  default     = []
}