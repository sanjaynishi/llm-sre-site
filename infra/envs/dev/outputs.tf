# infra/envs/dev/outputs.tf

output "agent_api_endpoint" {
  value       = module.agent_api.http_api_endpoint
  description = "Agent API endpoint"
}

output "agent_api_http_api_id" {
  value       = module.agent_api.http_api_id
  description = "API Gateway HTTP API id"
}

# IMPORTANT:
# Use the output name your agent_api module actually exports.
# In your earlier working state, you were outputting `agent_api_lambda_function_name`
# from the root module, so keep that, but point it to an attribute that EXISTS.
#
# If your module exports `lambda_function_name`, use that.
# If it exports `lambda_name`, use that.
#
# Try the first one below; if terraform errors, switch to the second.
output "agent_api_lambda_function_name" {
  value       = try(module.agent_api.lambda_function_name, module.agent_api.lambda_name)
  description = "Lambda function name"
}

# These should NOT come from module.agent_api (since it doesn't export them).
# Output them directly from root inputs (variables).
output "agent_config_bucket" {
  value       = var.agent_config_bucket
  description = "S3 bucket where agent config / knowledge live"
}

output "agent_config_prefix" {
  value       = var.agent_config_prefix
  description = "Prefix where agent config JSON is stored"
}

output "ui_s3_buckets" {
  value       = module.site.s3_buckets
  description = "Per-domain S3 buckets used for UI hosting"
}

output "cloudfront_domains" {
  value       = module.site.cloudfront_domains
  description = "Per-domain CloudFront distribution domains"
}

# ----------------------------
# Analytics outputs (only if module.analytics exists in dev)
# ----------------------------
output "analytics_bucket_name" {
  description = "Analytics S3 bucket name"
  value       = try(module.analytics.analytics_bucket_name, null)
}

output "analytics_bucket_domain_name" {
  description = "Bucket domain name required by CloudFront logging_config.bucket"
  value       = try(module.analytics.analytics_bucket_domain_name, null)
}

output "analytics_bucket_arn" {
  description = "ARN of analytics bucket"
  value       = try(module.analytics.analytics_bucket_arn, null)
}