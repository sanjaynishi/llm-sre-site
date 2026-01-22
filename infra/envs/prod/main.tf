# infra/envs/prod/main.tf

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

data "aws_caller_identity" "current" {}

# --- S3 bucket for agent config (shared by Lambda) ---
resource "aws_s3_bucket" "agent_config" {
  bucket = "llm-sre-agent-config-${var.env}-${data.aws_caller_identity.current.account_id}"
}

resource "aws_s3_bucket_public_access_block" "agent_config" {
  bucket                  = aws_s3_bucket.agent_config.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# --- Agent API (Lambda + HTTP API) ---
module "agent_api" {
  source = "../../modules/agent_api"

  env        = var.env
  aws_region = var.aws_region

  # ✅ OpenAI settings (same as dev)
  openai_api_key = var.openai_api_key
  openai_model   = var.openai_model

  # ✅ Config bucket for dropdowns / allowlists (same pattern as dev)
  agent_config_bucket = aws_s3_bucket.agent_config.bucket
  agent_config_prefix = "agent-config"

  # IMPORTANT: path from infra/envs/prod -> repo_root/services/agent_api
  lambda_src_dir = "${path.module}/../../../services/agent_api"
}

# --- Site (CloudFront) ---
module "site" {
  source              = "../../modules/site"
  aws_region          = var.aws_region
  acm_certificate_arn = var.acm_certificate_arn
  env                 = "prod"

  domains = {
    "aimlsre.com"     = "aimlsre.com"
    "www.aimlsre.com" = "www.aimlsre.com"
  }

  enable_placeholder = false

  # ✅ Always point to whatever API Terraform deployed (avoid hardcoding)
  api_domain_name = replace(replace(module.agent_api.http_api_endpoint, "https://", ""), "/", "")
}