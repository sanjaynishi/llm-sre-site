variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "acm_certificate_arn" {
  description = "ACM certificate ARN in us-east-1 covering the CloudFront aliases"
  type        = string
}

variable "env" {
  type = string
}

variable "enable_tf_ui_deploy" {
  description = "Whether Terraform should deploy UI artifacts (disabled when CI/CD is used)"
  type        = bool
  default     = false
}

variable "enable_placeholder" {
  type    = bool
  default = true
}

variable "domains" {
  description = "Map of domains (key and value can both be the domain). Using a map keeps for_each keys stable."
  type        = map(string)
}

variable "api_domain_name" {
  description = "Optional: API Gateway execute-api domain (no https://). Example: abc123.execute-api.us-east-1.amazonaws.com"
  type        = string
  default     = ""

  validation {
    condition     = var.api_domain_name == "" || !can(regex("^https?://", var.api_domain_name))
    error_message = "api_domain_name must NOT include http:// or https://"
  }
}

variable "analytics_bucket_domain_name" {
  type        = string
  description = "S3 bucket domain name for CloudFront logs, e.g. my-bucket.s3.amazonaws.com"
  default     = ""

  validation {
    condition     = var.analytics_bucket_domain_name == "" || can(regex("\\.s3(\\.[a-z0-9-]+)?\\.amazonaws\\.com$", var.analytics_bucket_domain_name))
    error_message = "analytics_bucket_domain_name must look like <bucket>.s3.amazonaws.com (or regional variant), or be empty."
  }
}

variable "name_prefix" {
  type        = string
  description = "Base name prefix for resources (e.g., llm-sre)"
}

variable "aws_account_id" {
  type        = string
  description = "AWS account id (12 digits), used for CloudFront SourceArn conditions"

  validation {
    condition     = can(regex("^[0-9]{12}$", var.aws_account_id))
    error_message = "aws_account_id must be a 12-digit AWS account id."
  }
}
