variable "env" {
  type        = string
  description = "Environment name (dev|prod)"
}

variable "name_prefix" {
  type        = string
  description = "Base name prefix for resources (e.g., llm-sre)"
}

variable "aws_account_id" {
  type        = string
  description = "AWS Account ID (used to make bucket name unique)"
}

variable "retention_days" {
  type        = number
  description = "How many days to retain CloudFront/APIGW logs in S3 (raw)"
  default     = 30
}

variable "cloudfront_account_id" {
  description = "CloudFront log-delivery account id used in bucket policy (only needed if you enable CloudFront standard logs)"
  type        = string
  default     = "114774131450"
}

variable "enable_cloudfront_log_write" {
  description = "Enable bucket policy that allows CloudFront standard logging to write into this bucket"
  type        = bool
  default     = false
}