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
  description = "How many days to retain CloudFront access logs in S3"
  default     = 30
}

variable "cloudfront_account_id" {
  description = "AWS-managed CloudFront log delivery account ID (global, fixed)"
  type        = string
  default     = "114774131450"
}

variable "enable_cloudfront_log_write" {
  description = "Enable CloudFront standard access logs into the analytics bucket"
  type        = bool
  default     = false
}