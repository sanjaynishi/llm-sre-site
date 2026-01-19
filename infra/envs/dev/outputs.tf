output "cloudfront_domains" {
  value = module.site.cloudfront_domains
}

output "s3_buckets" {
  value = module.site.s3_buckets
}

output "http_api_endpoint" {
  value       = module.agent_api.http_api_endpoint
  description = "HTTP API endpoint for agent_api (direct execute-api URL)"
}

output "http_api_id" {
  value       = module.agent_api.http_api_id
  description = "HTTP API ID for agent_api"
}

output "agent_api_lambda_name" {
  value       = module.agent_api.lambda_name
  description = "Lambda function name for agent_api"
}