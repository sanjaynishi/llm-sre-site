variable "env" { type = string }
variable "aws_region" { type = string }

variable "acm_certificate_arn" {
  type = string
}

variable "openai_api_key" {
  description = "OpenAI API key injected from GitHub Actions"
  type        = string
  sensitive   = true
}

variable "openai_model" {
  description = "OpenAI model for travel generation"
  type        = string
  default     = "gpt-5.2"
}

variable "agent_config_bucket" {
  type        = string
  description = "Existing S3 bucket for agent config and runbooks"
}

variable "s3_prefix" {
  type        = string
  description = "Prefix under the bucket (example: knowledge/)"
}

variable "agent_config_prefix" {
  type        = string
  description = "Prefix under the bucket (example: knowledge/)"
}

variable "lambda_image_uri" {
  type = string
}