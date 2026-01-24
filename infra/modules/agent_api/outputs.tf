# modules/agent_api/outputs.tf

output "lambda_function_name" {
  value = aws_lambda_function.agent_api.function_name
}

output "http_api_endpoint" {
  value = aws_apigatewayv2_api.http_api.api_endpoint
}

# If manage_ecr=false, this will output null (no ECR resource in TF state)
output "ecr_repository_url" {
  value       = var.manage_ecr ? aws_ecr_repository.agent_api[0].repository_url : null
  description = "ECR repository URL when Terraform manages the repo (manage_ecr=true)."
}

output "ecr_repository_name" {
  value       = var.manage_ecr ? aws_ecr_repository.agent_api[0].name : null
  description = "ECR repository name when Terraform manages the repo (manage_ecr=true)."
}