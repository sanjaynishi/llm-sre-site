# If not already there
#data "aws_caller_identity" "current" {}

variable "env" { type = string }
variable "aws_region" { type = string }

variable "region" {
  type    = string
  default = "us-east-1"
}

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

variable "manage_ecr" {
  type    = bool
  default = false
}

variable "name_prefix" {
  description = "Base name prefix for resources (e.g., llm-sre)"
  type        = string
  default     = "llm-sre"
}

variable "analytics_bucket_domain_name" {
  description = "S3 bucket domain name for CloudFront access logs (optional in dev)"
  type        = string
  default     = ""
}

# ------------------------------------
# RAG config
# ------------------------------------
variable "chroma_collection" {
  type        = string
  description = "Chroma collection name"
  default     = "runbooks_dev"
}

variable "embed_model" {
  type        = string
  description = "Embedding model for indexing/query"
  default     = "text-embedding-3-small"
}

variable "vectors_prefix" {
  type        = string
  description = "Prefix under agent_config_bucket where Chroma store files are uploaded"
}

variable "runbooks_prefix" {
  type        = string
  description = "Prefix under agent_config_bucket where runbook PDFs live"
}


