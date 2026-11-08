output "cluster_name" {
  description = "EKS cluster name, for aws eks update-kubeconfig."
  value       = aws_eks_cluster.this.name
}

output "image_repositories" {
  description = "ECR repository URLs by image."
  value       = { for name, repo in aws_ecr_repository.images : name => repo.repository_url }
}

output "database_endpoint" {
  description = "PostgreSQL host and port."
  value       = aws_db_instance.this.endpoint
}

output "database_secret_arn" {
  description = "Secrets Manager secret holding the generated database password."
  value       = aws_db_instance.this.master_user_secret[0].secret_arn
}
