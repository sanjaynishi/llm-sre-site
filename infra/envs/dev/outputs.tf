# infra/envs/dev/outputs.tf

output "agent_api_endpoint" {
  value = module.agent_api.http_api_endpoint
}

output "agent_api_lambda_function_name" {
  value = module.agent_api.lambda_function_name
}

output "ui_s3_buckets" {
  value = module.site.s3_buckets
}

output "cloudfront_domains" {
  value = module.site.cloudfront_domains
}