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

# ✅ Needed because site module now requires aws_account_id
data "aws_caller_identity" "current" {}

# --- Agent API first (site depends on its endpoint) ---
module "agent_api" {
  source = "../../modules/agent_api"

  # Required inputs
  env        = var.env
  aws_region = var.aws_region

  openai_api_key = var.openai_api_key
  openai_model   = var.openai_model

  # Lambda source code directory (used by CI docker build, not Terraform directly)
  lambda_src_dir = "${path.module}/../../../services/agent_api"

  # MUST be non-empty in CI (set by GitHub Actions)
  lambda_image_uri = var.lambda_image_uri

  # ECR not managed by TF in dev/prod (CI builds/pushes images)
  manage_ecr = false

  # ✅ Use EXISTING bucket (same bucket you upload JSON + runbooks to)
  agent_config_bucket = var.agent_config_bucket

  # ✅ Prefix for config JSON files
  agent_config_prefix = var.agent_config_prefix

  # ✅ Base knowledge prefix (e.g. "knowledge/")
  s3_prefix = var.s3_prefix
}

# --- Site (CloudFront) ---
module "site" {
  source              = "../../modules/site"
  aws_region          = var.aws_region
  acm_certificate_arn = var.acm_certificate_arn
  env                 = var.env

  enable_placeholder = false

  # ✅ REQUIRED by site module
  name_prefix    = var.name_prefix
  aws_account_id = data.aws_caller_identity.current.account_id

  # Convert endpoint to host string expected by site module
  api_domain_name = replace(replace(module.agent_api.http_api_endpoint, "https://", ""), "/", "")

  domains = {
    "dev.aimlsre.com" = "dev.aimlsre.com"
  }

  # ✅ Optional (safe). Only works if you added this variable + analytics module.
  # If var.analytics_bucket_domain_name isn't defined yet, try() prevents a hard failure.
  analytics_bucket_domain_name = try(var.analytics_bucket_domain_name, "")
}