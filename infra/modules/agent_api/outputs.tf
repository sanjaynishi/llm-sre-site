output "http_api_endpoint" {
  value = aws_apigatewayv2_api.http_api.api_endpoint
}

output "http_api_id" {
  value = aws_apigatewayv2_api.http_api.id
}

output "lambda_name" {
  value = aws_lambda_function.agent_api.function_name
}