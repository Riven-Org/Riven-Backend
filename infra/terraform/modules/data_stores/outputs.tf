output "postgres_endpoint" {
  description = "Connection endpoint for PostgreSQL"
  value       = aws_db_instance.postgres.endpoint
}

output "postgres_address" {
  description = "Host address for PostgreSQL"
  value       = aws_db_instance.postgres.address
}

output "postgres_port" {
  description = "Database port for PostgreSQL"
  value       = aws_db_instance.postgres.port
}

output "postgres_database_name" {
  description = "Name of the initial PostgreSQL database"
  value       = aws_db_instance.postgres.db_name
}

output "postgres_security_group_id" {
  description = "Security group ID attached to PostgreSQL"
  value       = aws_security_group.postgres.id
}

output "redis_primary_endpoint_address" {
  description = "Primary endpoint address for ElastiCache Redis"
  value       = aws_elasticache_replication_group.redis.primary_endpoint_address
}

output "redis_port" {
  description = "Port number for ElastiCache Redis"
  value       = aws_elasticache_replication_group.redis.port
}

output "redis_security_group_id" {
  description = "Security group ID attached to Redis"
  value       = aws_security_group.redis.id
}

output "artifacts_bucket_id" {
  description = "The ID of the S3 artifacts bucket"
  value       = aws_s3_bucket.artifacts.id
}

output "artifacts_bucket_arn" {
  description = "The ARN of the S3 artifacts bucket"
  value       = aws_s3_bucket.artifacts.arn
}
