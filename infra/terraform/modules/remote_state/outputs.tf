output "bucket_name" {
  description = "The name of the S3 bucket for remote state"
  value       = aws_s3_bucket.state.id
}

output "bucket_arn" {
  description = "The ARN of the S3 bucket for remote state"
  value       = aws_s3_bucket.state.arn
}

output "dynamodb_table_name" {
  description = "The name of the DynamoDB table for state locking"
  value       = aws_dynamodb_table.locks.id
}

output "dynamodb_table_arn" {
  description = "The ARN of the DynamoDB table for state locking"
  value       = aws_dynamodb_table.locks.arn
}
