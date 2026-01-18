output "s3_buckets" {
  value = { for d, b in aws_s3_bucket.site : d => b.bucket }
}

output "cloudfront_domains" {
  value = { for d, dist in aws_cloudfront_distribution.cdn : d => dist.domain_name }
}