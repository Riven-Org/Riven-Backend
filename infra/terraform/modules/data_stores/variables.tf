variable "name_prefix" {
  description = "Prefix for data store resource names (e.g. riven-staging)"
  type        = string
}

variable "vpc_id" {
  description = "VPC ID where data stores reside"
  type        = string
}

variable "private_subnet_ids" {
  description = "Private subnet IDs for RDS and ElastiCache subnet groups"
  type        = list(string)
}

variable "eks_security_group_id" {
  description = "Security group ID of the EKS cluster for ingress access"
  type        = string
}

variable "postgres_instance_class" {
  description = "Instance class for RDS PostgreSQL"
  type        = string
  default     = "db.t4g.micro"
}

variable "postgres_allocated_storage" {
  description = "Allocated storage in GB for RDS"
  type        = number
  default     = 20
}

variable "postgres_max_allocated_storage" {
  description = "Maximum storage limit in GB for RDS autoscaling"
  type        = number
  default     = 100
}

variable "postgres_database_name" {
  description = "Initial PostgreSQL database name"
  type        = string
  default     = "riven"
}

variable "postgres_username" {
  description = "Master username for PostgreSQL"
  type        = string
  default     = "riven"
}

variable "postgres_password" {
  description = "Master password for PostgreSQL"
  type        = string
  sensitive   = true
}

variable "redis_node_type" {
  description = "Node type for ElastiCache Redis"
  type        = string
  default     = "cache.t4g.micro"
}

variable "redis_num_cache_clusters" {
  description = "Number of cache clusters (nodes) in the Redis replication group"
  type        = number
  default     = 1
}

variable "artifacts_bucket_name" {
  description = "Name for the S3 object storage artifacts bucket"
  type        = string
}

variable "tags" {
  description = "Tags to attach to data store resources"
  type        = map(string)
  default     = {}
}
