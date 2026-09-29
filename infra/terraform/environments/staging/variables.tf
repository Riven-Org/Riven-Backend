variable "aws_region" {
  description = "AWS region for staging infrastructure"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Environment name"
  type        = string
  default     = "staging"
}

variable "postgres_password" {
  description = "Master password for staging RDS PostgreSQL (must not use development credentials)"
  type        = string
  sensitive   = true
}

variable "tags" {
  description = "Resource tags applied to all staging resources"
  type        = map(string)
  default = {
    Project     = "Riven"
    Environment = "staging"
    ManagedBy   = "Terraform"
  }
}
