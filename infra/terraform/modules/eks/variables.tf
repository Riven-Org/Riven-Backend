variable "name_prefix" {
  description = "Prefix for EKS resource names (e.g. riven-staging)"
  type        = string
}

variable "cluster_name" {
  description = "Name of the EKS cluster"
  type        = string
  default     = "riven-cluster"
}

variable "cluster_version" {
  description = "Kubernetes version for the EKS cluster"
  type        = string
  default     = "1.30"
}

variable "vpc_id" {
  description = "VPC ID where the cluster and node groups will reside"
  type        = string
}

variable "subnet_ids" {
  description = "Subnet IDs for the EKS control plane and worker nodes (private subnets recommended)"
  type        = list(string)
}

variable "app_node_instance_types" {
  description = "Instance types for standard application worker nodes"
  type        = list(string)
  default     = ["t3.medium"]
}

variable "app_node_desired_size" {
  description = "Desired number of application worker nodes"
  type        = number
  default     = 2
}

variable "app_node_min_size" {
  description = "Minimum number of application worker nodes"
  type        = number
  default     = 1
}

variable "app_node_max_size" {
  description = "Maximum number of application worker nodes"
  type        = number
  default     = 5
}

variable "sandbox_node_instance_types" {
  description = "Instance types for isolated sandbox runner nodes"
  type        = list(string)
  default     = ["t3.large"]
}

variable "sandbox_node_desired_size" {
  description = "Desired number of sandbox nodes"
  type        = number
  default     = 1
}

variable "sandbox_node_min_size" {
  description = "Minimum number of sandbox nodes"
  type        = number
  default     = 1
}

variable "sandbox_node_max_size" {
  description = "Maximum number of sandbox nodes"
  type        = number
  default     = 10
}

variable "tags" {
  description = "Tags to attach to EKS resources"
  type        = map(string)
  default     = {}
}
