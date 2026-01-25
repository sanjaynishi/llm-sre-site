# modules/agent_api/variables.tf

variable "env" { type = string }
variable "aws_region" { type = string }

variable "region" {
  type    = string
  default = "us-east-1"
}

variable "name_prefix" {
  type    = string
  default = "llm-sre"
}

variable "openai_api_key" {
  type      = string
  sensitive = true
}

variable "openai_model" {
  type    = string
  default = "gpt-5.2"
}

variable "lambda_src_dir" {
  type        = string
  description = "Path to services/agent_api (used by CI docker build, not by Terraform directly here)"
  default     = ""
}

variable "lambda_image_uri" {
  type        = string
  description = "Full ECR image URI including tag. Must be non-empty for Image Lambda."
}

variable "agent_config_bucket" { type = string }
variable "agent_config_prefix" { type = string }

variable "s3_prefix" {
  type        = string
  description = "Base prefix under the bucket, e.g. knowledge/"
  default     = "knowledge/"
}

variable "runbooks_prefix" {
  type        = string
  description = "Prefix for runbooks relative to S3_PREFIX (or full if you pass full)."
  default     = "runbooks/"
}

variable "vectors_prefix" {
  type        = string
  description = "Full S3 prefix to chroma store (recommended). Example: knowledge/vectors/prod/chroma/"
  default     = ""
}

variable "chroma_collection" {
  type        = string
  description = "Chroma collection name"
  default     = ""
}

variable "embed_model" {
  type    = string
  default = "text-embedding-3-small"
}

variable "agents_key" {
  type    = string
  default = "agents.json"
}

variable "cors_allow_origins" {
  type        = list(string)
  description = "Allowed CORS origins for API Gateway"
  default = [
    "https://dev.aimlsre.com",
    "https://aimlsre.com",
    "https://www.aimlsre.com"
  ]
}

# IMPORTANT:
# Keep only ONE manage_ecr variable. Default false so prod doesn't require ECR admin perms.
variable "manage_ecr" {
  type        = bool
  description = "If true, Terraform manages ECR repo + lifecycle policy. If false, it will NOT touch ECR."
  default     = false
}