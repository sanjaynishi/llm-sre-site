# infra/modules/agent_api/outputs.tf

output "http_api_endpoint" {
  description = "HTTP API base endpoint (includes https://)"
  value       = aws_apigatewayv2_api.http_api.api_endpoint
}

output "http_api_id" {
  description = "HTTP API id"
  value       = aws_apigatewayv2_api.http_api.id
}

output "lambda_name" {
  description = "Lambda function name"
  value       = aws_lambda_function.agent_api.function_name
}

# Optional: only if you manage ECR in this module with count
output "ecr_repository_url" {
  description = "ECR repository URL (only if manage_ecr=true)"
  value       = var.manage_ecr ? aws_ecr_repository.agent_api[0].repository_url : null
}