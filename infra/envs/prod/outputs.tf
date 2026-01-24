# infra/envs/prod/outputs.tf

output "agent_api_endpoint" {
  description = "Agent API endpoint"
  value       = module.agent_api.agent_api_endpoint
}

output "agent_api_lambda_function_name" {
  description = "Lambda function name"
  value       = module.agent_api.agent_api_lambda_function_name
}

output "ui_s3_buckets" {
  description = "Per-domain S3 buckets used for UI hosting"
  value       = module.site.ui_s3_buckets
}

output "cloudfront_domains" {
  description = "Per-domain CloudFront distribution domain names"
  value       = module.site.cloudfront_domains
}