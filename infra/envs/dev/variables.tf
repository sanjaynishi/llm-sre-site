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