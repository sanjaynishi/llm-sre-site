# infra/envs/prod/outputs.tf

output "agent_api_endpoint" {
  value       = module.agent_api.http_api_endpoint
  description = "Agent API endpoint"
}

output "agent_api_lambda_function_name" {
  value       = module.agent_api.lambda_function_name
  description = "Lambda function name"
}

output "cloudfront_domains" {
  value       = module.site.cloudfront_domains
  description = "Per-domain CloudFront distribution domains"
}

output "ui_s3_buckets" {
  value       = module.site.s3_buckets
  description = "Per-domain S3 buckets used for UI hosting"
}