output "s3_buckets" {
  description = "Map of domain => S3 bucket name used for UI hosting"
  value       = { for d, b in aws_s3_bucket.site : d => b.bucket }
}

output "cloudfront_domains" {
  description = "Map of domain => CloudFront distribution domain name"
  value       = { for d, dist in aws_cloudfront_distribution.cdn : d => dist.domain_name }
}