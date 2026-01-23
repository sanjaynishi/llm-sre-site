variable "env" {
  type = string
}

variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "name_prefix" {
  type    = string
  default = "llm-sre"
}

# Path to your lambda source folder (services/agent_api)
variable "lambda_src_dir" {
  type = string
}

# Optional: if you want CloudFront or other origins to call the API (wire later)
variable "allowed_origins" {
  type    = list(string)
  default = []
}

variable "openai_api_key" {
  description = "OpenAI API key injected from GitHub Actions"
  type        = string
  sensitive   = true
}

variable "openai_model" {
  description = "OpenAI model used by the agent API"
  type        = string
  default     = "gpt-5.2"
}

# ✅ Single bucket used for BOTH:
# - config JSON (agent-config/*)
# - runbooks PDFs (knowledge/runbooks/*)
variable "agent_config_bucket" {
  type        = string
  description = "Existing S3 bucket that stores agent config JSON and runbooks PDFs"
}

# Config JSON folder (agents.json, allowlists.json, etc.)
variable "agent_config_prefix" {
  type        = string
  description = "Prefix/folder in the bucket where config JSON files are stored (e.g., agent-config)"
  default     = "agent-config"
}

# Runbooks base prefix (e.g., knowledge/ → knowledge/runbooks/*.pdf)
variable "s3_prefix" {
  type        = string
  description = "Prefix under the bucket for docs/runbooks (e.g., knowledge/)"
  default     = "knowledge/"
}

variable "lambda_image_uri" {
  type        = string
  description = "ECR image URI for the agent_api Lambda container"
}