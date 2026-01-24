# infra/modules/agent_api/outputs.tf
output "http_api_endpoint" {
  value = aws_apigatewayv2_api.http_api.api_endpoint
}

output "http_api_id" {
  value = aws_apigatewayv2_api.http_api.id
}

output "lambda_function_name" {
  value = aws_lambda_function.agent_api.function_name
}

# Only present if manage_ecr=true, otherwise null
output "ecr_repository_url" {
  value = var.manage_ecr ? aws_ecr_repository.agent_api[0].repository_url : null
}
