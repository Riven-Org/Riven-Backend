# --- Cluster IAM Role -----------------------------------------------------------------

resource "aws_iam_role" "cluster" {
  name = "${var.name_prefix}-eks-cluster-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "eks.amazonaws.com"
        }
      }
    ]
  })

  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "cluster_policy" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy"
  role       = aws_iam_role.cluster.name
}

# --- KMS Key for Secret Encryption ----------------------------------------------------

resource "aws_kms_key" "eks" {
  description             = "EKS Secret Encryption Key for ${var.cluster_name}"
  deletion_window_in_days = 7
  enable_key_rotation     = true

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-eks-key"
  })
}

# --- EKS Cluster ----------------------------------------------------------------------

resource "aws_eks_cluster" "main" {
  name     = var.cluster_name
  version  = var.cluster_version
  role_arn = aws_iam_role.cluster.arn

  vpc_config {
    subnet_ids              = var.subnet_ids
    endpoint_private_access = true
    endpoint_public_access  = true
  }

  encryption_config {
    provider {
      key_arn = aws_kms_key.eks.arn
    }
    resources = ["secrets"]
  }

  depends_on = [
    aws_iam_role_policy_attachment.cluster_policy,
  ]

  tags = merge(var.tags, {
    Name = var.cluster_name
  })
}

# --- Node Groups IAM Role -------------------------------------------------------------

resource "aws_iam_role" "nodes" {
  name = "${var.name_prefix}-eks-node-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ec2.amazonaws.com"
        }
      }
    ]
  })

  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "node_worker_policy" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy"
  role       = aws_iam_role.nodes.name
}

resource "aws_iam_role_policy_attachment" "node_cni_policy" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy"
  role       = aws_iam_role.nodes.name
}

resource "aws_iam_role_policy_attachment" "node_registry_policy" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
  role       = aws_iam_role.nodes.name
}

# --- Standard Applications Node Group -------------------------------------------------

resource "aws_eks_node_group" "apps" {
  cluster_name    = aws_eks_cluster.main.name
  node_group_name = "${var.name_prefix}-app-nodes"
  node_role_arn   = aws_iam_role.nodes.arn
  subnet_ids      = var.subnet_ids

  instance_types = var.app_node_instance_types

  scaling_config {
    desired_size = var.app_node_desired_size
    min_size     = var.app_node_min_size
    max_size     = var.app_node_max_size
  }

  labels = {
    "riven.org/workload" = "apps"
  }

  depends_on = [
    aws_iam_role_policy_attachment.node_worker_policy,
    aws_iam_role_policy_attachment.node_cni_policy,
    aws_iam_role_policy_attachment.node_registry_policy,
  ]

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-app-nodes"
  })
}

# --- Isolated Sandbox Node Group (Ticket S02.4.2) ---------------------------------------

resource "aws_eks_node_group" "sandbox" {
  cluster_name    = aws_eks_cluster.main.name
  node_group_name = "${var.name_prefix}-sandbox-nodes"
  node_role_arn   = aws_iam_role.nodes.arn
  subnet_ids      = var.subnet_ids

  instance_types = var.sandbox_node_instance_types

  scaling_config {
    desired_size = var.sandbox_node_desired_size
    min_size     = var.sandbox_node_min_size
    max_size     = var.sandbox_node_max_size
  }

  labels = {
    "riven.org/workload" = "sandbox"
  }

  taint {
    key    = "dedicated"
    value  = "sandbox"
    effect = "NO_SCHEDULE"
  }

  depends_on = [
    aws_iam_role_policy_attachment.node_worker_policy,
    aws_iam_role_policy_attachment.node_cni_policy,
    aws_iam_role_policy_attachment.node_registry_policy,
  ]

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-sandbox-nodes"
  })
}
