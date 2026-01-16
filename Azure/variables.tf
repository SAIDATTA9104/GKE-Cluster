variable "subscription_id" {
  description = "The Azure Subscription ID (passed from ADO Pipeline)"
  type        = string
}

variable "resource_group_name" {
  description = "The name of the resource group"
  type        = string
}

variable "email_address" {
  description = "Email address for the alerts"
  type        = string
}


variable "location" {
  description = "The Azure region where resources will be deployed"
  type        = string
  default     = "global" # Choose your desired default Azure region
}

variable "action_group_name" {
    description = "The name of the Action Group"
    type        = string
}

variable "alert_name" {
    description = "The name of the Activity Log Alert"
    type        = string
}