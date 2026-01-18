variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "domains" {
  type    = set(string)
  default = ["sanjaynishi.com", "snrcs.com"]
}

variable "acm_certificate_arn" {
  description = "ACM certificate ARN in us-east-1 covering both domains"
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