# infra/envs/dev/main.tf

terraform {
  required_version = ">= 1.5.0"
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

# ✅ Required by s3_agent_config.tf and for passing aws_account_id into modules/site + modules/analytics
data "aws_caller_identity" "current" {}

# ============================================================
# Analytics (single bucket; CloudFront logs for dev/prod can land here)
# ============================================================
module "analytics" {
  source = "../../modules/analytics"

  env            = var.env
  name_prefix    = var.name_prefix
  aws_account_id = data.aws_caller_identity.current.account_id

  # ✅ Turn ON so CloudFront can write standard access logs
  enable_cloudfront_log_write = true

  # Optional: keep default 30 days or set explicitly
  # retention_days = 30
}

# ============================================================
# Agent API (Site depends on API endpoint for /api/* origin)
# ============================================================
module "agent_api" {
  source = "../../modules/agent_api"

  env        = var.env
  aws_region = var.aws_region
  region      = var.region   # ✅ ADD THIS

  name_prefix = var.name_prefix

  # OpenAI
  openai_api_key = var.openai_api_key
  openai_model   = var.openai_model

  # Container-image Lambda (built/pushed by CI)
  lambda_src_dir   = "${path.module}/../../../services/agent_api"
  lambda_image_uri = var.lambda_image_uri

  # ECR managed by CI (not Terraform)
  manage_ecr = false

  agent_config_bucket = var.agent_config_bucket
  agent_config_prefix = var.agent_config_prefix
  s3_prefix           = var.s3_prefix

  # RAG layout (dev)
  runbooks_prefix   = var.runbooks_prefix
  vectors_prefix    = var.vectors_prefix
  chroma_collection = var.chroma_collection
  embed_model       = var.embed_model

  agents_key = "agents.json"

  cors_allow_origins = [
    "https://dev.aimlsre.com",
    "https://aimlsre.com",
    "https://www.aimlsre.com",
  ]
}

# ============================================================
# Site (CloudFront + S3)
# ============================================================
module "site" {
  source              = "../../modules/site"
  aws_region          = var.aws_region
  acm_certificate_arn = var.acm_certificate_arn
  env                 = var.env

  enable_placeholder = false

  # ✅ REQUIRED by site module
  name_prefix    = var.name_prefix
  aws_account_id = data.aws_caller_identity.current.account_id

  # ✅ PASS REAL bucket-domain-name so logging_config is rendered
  analytics_bucket_domain_name = module.analytics.analytics_bucket_domain_name

  # API GW hostname for CloudFront origin (no scheme, no trailing slash)
  api_domain_name = replace(replace(module.agent_api.http_api_endpoint, "https://", ""), "/", "")

  domains = {
    "dev.aimlsre.com" = "dev.aimlsre.com"
  }
}