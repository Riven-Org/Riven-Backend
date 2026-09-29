# ==============================================================================
# Managed PostgreSQL (with pgvector support, Ticket S02.4.3)
# ==============================================================================

resource "aws_db_subnet_group" "postgres" {
  name       = "${var.name_prefix}-db-subnets"
  subnet_ids = var.private_subnet_ids

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-db-subnets"
  })
}

resource "aws_security_group" "postgres" {
  name        = "${var.name_prefix}-postgres-sg"
  description = "Allow inbound PostgreSQL traffic from EKS cluster"
  vpc_id      = var.vpc_id

  ingress {
    description     = "PostgreSQL from EKS cluster nodes"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [var.eks_security_group_id]
  }

  egress {
    description = "Allow all outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-postgres-sg"
  })
}

resource "aws_db_parameter_group" "pgvector" {
  name   = "${var.name_prefix}-pg16-vector"
  family = "postgres16"

  # Enables the pgvector extension support for embedding storage (causal graph & verifier)
  parameter {
    name         = "shared_preload_libraries"
    value        = "vector"
    apply_method = "pending-reboot"
  }

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-pg16-vector"
  })
}

resource "aws_db_instance" "postgres" {
  identifier             = "${var.name_prefix}-postgres"
  engine                 = "postgres"
  engine_version         = "16.3"
  instance_class         = var.postgres_instance_class
  allocated_storage      = var.postgres_allocated_storage
  max_allocated_storage  = var.postgres_max_allocated_storage
  db_name                = var.postgres_database_name
  username               = var.postgres_username
  password               = var.postgres_password
  db_subnet_group_name   = aws_db_subnet_group.postgres.name
  vpc_security_group_ids = [aws_security_group.postgres.id]
  parameter_group_name   = aws_db_parameter_group.pgvector.name

  storage_type               = "gp3"
  storage_encrypted          = true
  deletion_protection        = false
  skip_final_snapshot        = true
  publicly_accessible        = false
  auto_minor_version_upgrade = true

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-postgres"
  })
}

# ==============================================================================
# Managed Redis (ElastiCache, Ticket S02.4.3)
# ==============================================================================

resource "aws_elasticache_subnet_group" "redis" {
  name       = "${var.name_prefix}-redis-subnets"
  subnet_ids = var.private_subnet_ids

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-redis-subnets"
  })
}

resource "aws_security_group" "redis" {
  name        = "${var.name_prefix}-redis-sg"
  description = "Allow inbound Redis traffic from EKS cluster"
  vpc_id      = var.vpc_id

  ingress {
    description     = "Redis from EKS cluster nodes"
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [var.eks_security_group_id]
  }

  egress {
    description = "Allow all outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-redis-sg"
  })
}

resource "aws_elasticache_replication_group" "redis" {
  replication_group_id = "${var.name_prefix}-redis"
  description          = "Redis replication group for events and caching"
  node_type            = var.redis_node_type
  num_cache_clusters   = var.redis_num_cache_clusters
  port                 = 6379
  engine_version       = "7.1"
  parameter_group_name = "default.redis7"

  subnet_group_name  = aws_elasticache_subnet_group.redis.name
  security_group_ids = [aws_security_group.redis.id]

  at_rest_encryption_enabled = true
  transit_encryption_enabled = true

  automatic_failover_enabled = var.redis_num_cache_clusters > 1 ? true : false

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-redis"
  })
}

# ==============================================================================
# Managed S3 Object Storage for Artifacts (ADR 0011, Ticket S02.4.3)
# ==============================================================================

resource "aws_s3_bucket" "artifacts" {
  bucket        = var.artifacts_bucket_name
  force_destroy = false

  tags = merge(var.tags, {
    Name    = var.artifacts_bucket_name
    Purpose = "Verification run logs and artifacts"
  })
}

resource "aws_s3_bucket_versioning" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
