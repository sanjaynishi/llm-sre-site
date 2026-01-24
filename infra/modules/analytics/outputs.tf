output "analytics_bucket_name" {
  description = "Name of the S3 bucket storing CloudFront access logs"
  value       = aws_s3_bucket.analytics.bucket
}

output "analytics_bucket_domain_name" {
  description = "Bucket domain name required by CloudFront logging_config.bucket (must be bucket-domain-name)"
  value       = aws_s3_bucket.analytics.bucket_domain_name
}

output "analytics_bucket_arn" {
  description = "ARN of the analytics bucket"
  value       = aws_s3_bucket.analytics.arn
}

output "analytics_bucket" {
  value = aws_s3_bucket.analytics.bucket
}