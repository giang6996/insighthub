variable "aws_region" {
  description = "AWS region for the demo deployment."
  type        = string
  default     = "ap-southeast-1"
}

variable "project_name" {
  description = "Project name used in resource names and tags."
  type        = string
  default     = "insighthub"
}

variable "environment" {
  description = "Deployment environment name."
  type        = string
  default     = "day3"
}

variable "vpc_cidr" {
  description = "CIDR range for the InsightHub VPC."
  type        = string
  default     = "10.20.0.0/16"
}

variable "availability_zone_count" {
  description = "Number of AZs used by the demo network."
  type        = number
  default     = 2

  validation {
    condition     = var.availability_zone_count == 2
    error_message = "The Day 3 foundation requires exactly two Availability Zones."
  }
}

variable "availability_zone_names" {
  description = "Stable Availability Zone names allowlisted for this demo region."
  type        = list(string)
  default     = ["ap-southeast-1a", "ap-southeast-1b"]

  validation {
    condition     = length(var.availability_zone_names) == 2
    error_message = "The Day 3 foundation requires exactly two explicitly named Availability Zones."
  }
}

variable "github_repository" {
  description = "GitHub owner/repository allowed to assume the IaC OIDC role."
  type        = string
  default     = "example/example"

  validation {
    condition     = can(regex("^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", var.github_repository))
    error_message = "github_repository must use the owner/repository format."
  }
}

variable "efs_csi_addon_version" {
  description = "Pinned EFS CSI add-on version compatible with the configured EKS version."
  type        = string
  default     = "v3.4.2-eksbuild.1"
}

variable "secrets_store_provider_addon_version" {
  description = "Pinned Secrets Store CSI provider add-on version verified for the Day 3 EKS baseline."
  type        = string
  default     = "v3.1.3-eksbuild.1"
}
