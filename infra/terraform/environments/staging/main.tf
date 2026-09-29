provider "aws" {
  region = var.aws_region

  default_tags {
    tags = var.tags
  }
}

locals {
  name_prefix  = "riven-${var.environment}"
  cluster_name = "riven-${var.environment}-cluster"
}

# --- Networking (VPC, Subnets, NAT, Route Tables) -------------------------------------

module "vpc" {
  source = "../../modules/vpc"

  name_prefix          = local.name_prefix
  cluster_name         = local.cluster_name
  vpc_cidr             = "10.10.0.0/16"
  availability_zones   = ["${var.aws_region}a", "${var.aws_region}b"]
  public_subnet_cidrs  = ["10.10.1.0/24", "10.10.2.0/24"]
  private_subnet_cidrs = ["10.10.11.0/24", "10.10.12.0/24"]
  tags                 = var.tags
}

# --- Compute (EKS Cluster, App Nodes, Isolated Sandbox Nodes) -------------------------

module "eks" {
  source = "../../modules/eks"

  name_prefix  = local.name_prefix
  cluster_name = local.cluster_name
  vpc_id       = module.vpc.vpc_id
  subnet_ids   = module.vpc.private_subnet_ids

  app_node_instance_types     = ["t3.medium"]
  app_node_desired_size       = 2
  app_node_min_size           = 1
  app_node_max_size           = 4
  sandbox_node_instance_types = ["t3.large"]
  sandbox_node_desired_size   = 1
  sandbox_node_min_size       = 1
  sandbox_node_max_size       = 6

  tags = var.tags
}

# --- Data Stores (RDS Postgres with pgvector, Redis, S3 Artifacts) --------------------

module "data_stores" {
  source = "../../modules/data_stores"

  name_prefix           = local.name_prefix
  vpc_id                = module.vpc.vpc_id
  private_subnet_ids    = module.vpc.private_subnet_ids
  eks_security_group_id = module.eks.cluster_security_group_id

  postgres_instance_class        = "db.t4g.micro"
  postgres_allocated_storage     = 20
  postgres_max_allocated_storage = 100
  postgres_database_name         = "riven"
  postgres_username              = "riven"
  postgres_password              = var.postgres_password

  redis_node_type          = "cache.t4g.micro"
  redis_num_cache_clusters = 1

  artifacts_bucket_name = "riven-artifacts-${var.environment}"
  tags                  = var.tags
}
