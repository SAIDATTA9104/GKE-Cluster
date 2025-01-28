variable "project_id" {
  description = "The project ID where the GKE cluster will be created"
  type        = string
}

variable "region" {
  description = "The region where the GKE cluster will be created"
  type        = string
}

variable "cluster_name" {
  description = "Name of the GKE cluster"
  type        = string
}

variable "network_project_id" {
  description = "The project ID where the Shared VPC exists"
  type        = string
}

variable "network_name" {
  description = "Name of the Shared VPC network"
  type        = string
}

variable "subnet_name" {
  description = "Name of the subnet in the Shared VPC"
  type        = string
}

variable "master_ipv4_cidr_block" {
  description = "The IP range for the master network"
  type        = string
}

variable "master_authorized_networks" {
  description = "List of CIDRs that can access the master"
  type = list(object({
    cidr_block   = string
    display_name = string
  }))
}

variable "labels" {
  description = "Labels to apply to the cluster"
  type        = map(string)
  default     = {}
}

variable "release_channel" {
  description = "Release channel for GKE cluster"
  type        = string
  default     = "REGULAR"
}