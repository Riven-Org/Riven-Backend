output "cluster_name" {
  description = "The name of the EKS cluster"
  value       = aws_eks_cluster.main.name
}

output "cluster_endpoint" {
  description = "The endpoint for the EKS Kubernetes API"
  value       = aws_eks_cluster.main.endpoint
}

output "cluster_certificate_authority_data" {
  description = "The base64 encoded certificate data required to communicate with the cluster"
  value       = aws_eks_cluster.main.certificate_authority[0].data
}

output "cluster_arn" {
  description = "The ARN of the EKS cluster"
  value       = aws_eks_cluster.main.arn
}

output "cluster_security_group_id" {
  description = "Security group ID attached to the EKS cluster"
  value       = aws_eks_cluster.main.vpc_config[0].cluster_security_group_id
}

output "node_role_arn" {
  description = "IAM role ARN used by the worker nodes"
  value       = aws_iam_role.nodes.arn
}

output "app_node_group_arn" {
  description = "ARN of the standard applications node group"
  value       = aws_eks_node_group.apps.arn
}

output "sandbox_node_group_arn" {
  description = "ARN of the isolated sandbox node group"
  value       = aws_eks_node_group.sandbox.arn
}
