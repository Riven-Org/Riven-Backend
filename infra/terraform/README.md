# Riven Infrastructure as Code (Ticket S02.4)

This directory contains the Terraform modules and environment configurations for Riven's cloud infrastructure.

---

## Architecture Overview

```
infra/terraform/
├── modules/
│   ├── remote_state/      # S3 bucket + DynamoDB table for Terraform remote state locking
│   ├── vpc/               # Multi-AZ VPC with public & private subnets, NAT gateway, EKS tags
│   ├── eks/               # EKS cluster, apps node pool, and dedicated isolated sandbox node pool
│   └── data_stores/       # RDS PostgreSQL (pgvector enabled), ElastiCache Redis, S3 artifacts
└── environments/
    └── staging/           # Staging environment composition and configuration
```

### Key Design & Security Principles

1. **Strict Multi-Account Isolation:** Staging and production reside in separate AWS accounts (AWS Organizations) with zero cross-environment IAM roles (ADR 0012).
2. **Private Networking:** All compute (EKS nodes) and data stores (RDS, Redis) run in private subnets with no public IP addresses. Egress is mediated via NAT Gateways.
3. **Isolated Sandbox Workload Pool (Ticket S02.4.2):**
   - Untrusted customer and AI-generated code execution runs on dedicated sandbox worker nodes.
   - Tainted with `dedicated=sandbox:NoSchedule`.
   - Labeled with `riven.org/workload=sandbox`.
   - Prevents tenant execution workloads from colocating with core API or orchestrator pods.
4. **Data Stores (Ticket S02.4.3):**
   - **PostgreSQL 16** with custom parameter group enabling `pgvector` (`shared_preload_libraries = "vector"`).
   - **ElastiCache Redis 7** with transit and at-rest encryption.
   - **S3 Object Storage** with AES256 server-side encryption and complete public access blocking.
5. **Remote State Locking (Ticket S02.4.1):**
   - S3 bucket with versioning and encryption.
   - DynamoDB lock table preventing concurrent applies.

---

## Administrator Runbook: Bootstrapping Staging from Zero

Follow these steps with active AWS administrative credentials in the dedicated **staging** AWS account:

### 1. Bootstrap Remote State Backend

Before using the S3 backend for staging, create the state storage and lock table:

```bash
cd infra/terraform/modules/remote_state

# Plan and apply the bootstrap state resources
terraform init
terraform plan -var="name_prefix=riven-tfstate-staging"
terraform apply -var="name_prefix=riven-tfstate-staging"
```

Note the created S3 bucket and DynamoDB table names.

### 2. Configure Staging Backend

Copy the example backend in `infra/terraform/environments/staging/`:

```bash
cd ../../environments/staging
cp backend.tf.example backend.tf
```

Ensure `backend.tf` references the bucket and table created in step 1:

```hcl
terraform {
  backend "s3" {
    bucket         = "riven-tfstate-staging-bucket"
    key            = "staging/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "riven-tfstate-staging-locks"
    encrypt        = true
  }
}
```

### 3. Configure Variables

Create `terraform.tfvars` from `terraform.tfvars.example`:

```bash
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars` to supply a strong, randomly generated database master password (e.g., from AWS Secrets Manager or password generator). Never commit `terraform.tfvars`.

### 4. Initialize, Plan, and Apply

```bash
# Initialize with the configured S3 remote backend
terraform init

# Review execution plan
terraform plan -out=staging.tfplan

# Apply the plan (requires explicit approval)
terraform apply staging.tfplan
```

### 5. Verify Staging Infrastructure

1. **EKS Cluster & Isolated Sandbox Nodes:**
   ```bash
   aws eks update-kubeconfig --name riven-staging-cluster --region us-east-1
   kubectl get nodes -L riven.org/workload
   kubectl describe nodes -l riven.org/workload=sandbox | grep -i taint
   ```
   *Expected:* Sandbox nodes display taint `dedicated=sandbox:NoSchedule`.

2. **RDS PostgreSQL & pgvector:**
   Connect via a bastion or internal pod:
   ```sql
   psql -h <postgres_endpoint> -U riven -d riven
   CREATE EXTENSION IF NOT EXISTS vector;
   SELECT * FROM pg_extension WHERE extname = 'vector';
   ```

3. **ElastiCache Redis:**
   ```bash
   redis-cli -h <redis_endpoint> -p 6379 ping
   ```
   *Expected:* `PONG`.

4. **S3 Artifacts Bucket:**
   ```bash
   aws s3api get-public-access-block --bucket riven-artifacts-staging
   ```
   *Expected:* All public access block fields set to `true`.
