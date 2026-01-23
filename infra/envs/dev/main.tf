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

  # Required inputs
  env        = var.env
  aws_region = var.aws_region

  openai_api_key = var.openai_api_key
  openai_model   = var.openai_model

  # Lambda source code directory
  lambda_src_dir = "${path.module}/../../../services/agent_api"

  lambda_image_uri = var.lambda_image_uri

  # ✅ Use EXISTING bucket (same bucket you upload JSON + runbooks to)
  agent_config_bucket = var.agent_config_bucket

  # ✅ Prefix for config JSON files (what you said is working)
  agent_config_prefix = var.agent_config_prefix

  # ✅ Prefix for runbooks/docs (knowledge/runbooks/*.pdf)
  s3_prefix = var.s3_prefix
}

# --- Site (CloudFront) ---
module "site" {
  source              = "../../modules/site"
  aws_region          = var.aws_region
  acm_certificate_arn = var.acm_certificate_arn
  env                 = var.env

  enable_placeholder = false

  # Example module output: https://xxxx.execute-api.us-east-1.amazonaws.com
  # Convert to host string expected by site module
  api_domain_name = replace(replace(module.agent_api.http_api_endpoint, "https://", ""), "/", "")

  domains = {
    "dev.aimlsre.com" = "dev.aimlsre.com"
  }
}