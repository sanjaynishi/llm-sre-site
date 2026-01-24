# infra/envs/prod/outputs.tf

output "agent_api_endpoint" {
  description = "HTTP API endpoint (APIGW v2)"
  value       = module.agent_api.http_api_endpoint
}

output "agent_api_lambda_function_name" {
  description = "Lambda function name for the Agent API"
  value       = module.agent_api.lambda_function_name
}

output "ui_s3_buckets" {
  description = "S3 buckets created for UI hosting per domain"
  value       = module.site.s3_buckets
}

output "cloudfront_domains" {
  description = "CloudFront distribution domain names per domain"
  value       = module.site.cloudfront_domains
}

# Only present when manage_ecr=true in the module
output "agent_api_ecr_repository_url" {
  description = "ECR repo URL when Terraform manages it"
  value       = module.agent_api.ecr_repository_url
}