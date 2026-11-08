variable "region" {
  description = "AWS region to deploy into."
  type        = string
  default     = "me-central-1"
}

variable "environment" {
  description = "Environment name, used in resource names."
  type        = string
  default     = "demo"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,18}$", var.environment))
    error_message = "Use 2 to 19 lowercase letters, digits or hyphens, starting with a letter."
  }
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC."
  type        = string
  default     = "10.40.0.0/16"
}

variable "kubernetes_version" {
  description = "EKS control plane version."
  type        = string
  default     = "1.31"
}

variable "api_public_cidrs" {
  description = "Networks allowed to reach the Kubernetes API over the internet. Empty keeps the endpoint private."
  type        = list(string)
  default     = []

  validation {
    condition     = !contains(var.api_public_cidrs, "0.0.0.0/0")
    error_message = "Do not open the Kubernetes API to the whole internet."
  }
}

variable "node_instance_type" {
  description = "Instance type for the EKS node group."
  type        = string
  default     = "t3.medium"
}

variable "node_count" {
  description = "Desired number of worker nodes."
  type        = number
  default     = 2

  validation {
    condition     = var.node_count >= 1 && var.node_count <= 10
    error_message = "Use between 1 and 10 nodes."
  }
}

variable "db_instance_class" {
  description = "RDS instance class."
  type        = string
  default     = "db.t4g.small"
}

variable "db_allocated_storage_gb" {
  description = "RDS storage in GiB."
  type        = number
  default     = 20
}

variable "db_multi_az" {
  description = "Run a standby database in a second availability zone."
  type        = bool
  default     = false
}

variable "deletion_protection" {
  description = "Prevent the database from being destroyed."
  type        = bool
  default     = true
}
