variable "aws_region" {
  type    = string
  default = "us-east-1"
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
}