output "vpc_id" {
  description = "The VPC ID"
  value       = module.vpc.vpc_id
}

output "eks_cluster_name" {
  description = "Name of the EKS cluster"
  value       = module.eks.cluster_name
}

output "eks_cluster_endpoint" {
  description = "Kubernetes API endpoint for the EKS cluster"
  value       = module.eks.cluster_endpoint
}

output "postgres_endpoint" {
  description = "RDS PostgreSQL endpoint"
  value       = module.data_stores.postgres_endpoint
}

output "redis_endpoint" {
  description = "ElastiCache Redis primary endpoint"
  value       = module.data_stores.redis_primary_endpoint_address
}

output "artifacts_bucket" {
  description = "S3 bucket for logs and artifacts"
  value       = module.data_stores.artifacts_bucket_id
}
