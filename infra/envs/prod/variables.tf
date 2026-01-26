variable "env" {
  type        = string
  description = "Environment name (dev|prod)"
}

variable "aws_region" {
  type        = string
  description = "AWS region (CloudFront cert must be in us-east-1)"
}

# ------------------------------------
# Domains
# ------------------------------------
variable "domains" {
  type        = list(string)
  description = "CloudFront aliases / site domains (e.g., [\"aimlsre.com\", \"www.aimlsre.com\"])"
}

# ------------------------------------
# TLS / ACM (required for custom domains in CloudFront)
# ------------------------------------
variable "acm_certificate_arn" {
  type        = string
  description = "ACM cert ARN in us-east-1 for CloudFront. Must cover ALL var.domains."
  default     = ""
}

# ------------------------------------
# OpenAI
# ------------------------------------
variable "openai_api_key" {
  description = "OpenAI API key injected from CI/CD (do NOT hardcode in tfvars committed to git)"
  type        = string
  sensitive   = true
  default     = ""
}

variable "openai_model" {
  description = "OpenAI model used by the Lambda."
  type        = string
  default     = "gpt-5.2"
}

# ------------------------------------
# Naming
# ------------------------------------
variable "name_prefix" {
  type        = string
  description = "Base prefix for resources (e.g., llm-sre)"
}

# ------------------------------------
# Buckets / prefixes
# ------------------------------------
variable "agent_config_bucket" {
  type        = string
  description = "S3 bucket for agent-config + runbooks + vectors"
}

variable "s3_prefix" {
  type        = string
  description = "Base prefix under agent_config_bucket (e.g., knowledge/)"
}

variable "agent_config_prefix" {
  type        = string
  description = "Prefix under agent_config_bucket for config JSON (e.g., agent-config)"
}

variable "vectors_prefix" {
  type        = string
  description = "Prefix under agent_config_bucket where Chroma store files are uploaded"
}

variable "runbooks_prefix" {
  type        = string
  description = "Prefix under agent_config_bucket where runbook PDFs live"
}

variable "region" {
  type    = string
  default = "us-east-1"
}

# ------------------------------------
# RAG config
# ------------------------------------
variable "chroma_collection" {
  type        = string
  description = "Chroma collection name"
  default     = "runbooks_prod"
}

variable "embed_model" {
  type        = string
  description = "Embedding model for indexing/query"
  default     = "text-embedding-3-small"
}

# ------------------------------------
# Lambda image
# ------------------------------------
variable "lambda_image_uri" {
  type        = string
  description = "Full ECR image URI. Strongly recommended to set from CI (e.g., <acct>.dkr.ecr.../repo:sha)."
  default     = ""
}

# Keep this for CI compatibility if you want, but do NOT pass to module unless module supports it.
variable "lambda_image_tag" {
  type        = string
  description = "ECR image tag used only if your module constructs URI itself (module must support it)."
  default     = "latest"
}


variable "ui_bucket_name" {
  type    = string
  default = ""
}

variable "analytics_bucket_domain_name" {
  type = string
}
