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

# --- Agent API first (site depends on its endpoint) ---
module "agent_api" {
  source = "../../modules/agent_api"

  openai_api_key = var.openai_api_key
  openai_model   = "gpt-5.1-mini"
  env            = var.env
  aws_region     = var.aws_region

  lambda_src_dir = "${path.module}/../../../services/agent_api"

  # ✅ Add these 2 lines
  agent_config_bucket = aws_s3_bucket.agent_config.bucket
  agent_config_prefix = "agent-config"
}

# --- Site (CloudFront) ---
module "site" {
  source              = "../../modules/site"
  aws_region          = var.aws_region
  acm_certificate_arn = var.acm_certificate_arn
  env                 = "dev"

  enable_placeholder = false

  api_domain_name = replace(replace(module.agent_api.http_api_endpoint, "https://", ""), "/", "")

  domains = {
    "dev.aimlsre.com" = "dev.aimlsre.com"
  }
}