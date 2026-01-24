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

# ✅ Needed because site module now requires aws_account_id
data "aws_caller_identity" "current" {}

# ============================================================
# Agent API (Site depends on API endpoint for /api/* origin)
# ============================================================
module "agent_api" {
  source = "../../modules/agent_api"

  # Required
  env        = var.env
  aws_region = var.aws_region

  # Naming (optional in module, but good to pass)
  name_prefix = var.name_prefix

  # OpenAI
  openai_api_key = var.openai_api_key
  openai_model   = var.openai_model

  # Container-image Lambda
  lambda_src_dir   = "${path.module}/../../../services/agent_api"
  lambda_image_uri = var.lambda_image_uri

  # ECR not managed by TF in dev/prod (CI builds/pushes images)
  manage_ecr = false

  # Config / knowledge bucket + prefixes
  agent_config_bucket = var.agent_config_bucket
  agent_config_prefix = var.agent_config_prefix

  # Knowledge layout
  s3_prefix         = var.s3_prefix
  runbooks_prefix   = var.runbooks_prefix
  vectors_prefix    = var.vectors_prefix
  chroma_collection = var.chroma_collection
  embed_model       = var.embed_model

  # Optional
  agents_key = "agents.json"

  # CORS (prod + dev)
  cors_allow_origins = [
    "https://aimlsre.com",
    "https://www.aimlsre.com",
    "https://dev.aimlsre.com",
  ]
}

# ============================================================
# Site (CloudFront + S3)
# One distribution per domain in var.domains
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

  # API GW hostname for CloudFront origin (no scheme, no trailing slash)
  api_domain_name = replace(replace(module.agent_api.http_api_endpoint, "https://", ""), "/", "")

  # module.site expects map(string)
  domains = { for d in var.domains : d => d }

  # ✅ Optional (safe). Only works if you added this variable + analytics module.
  analytics_bucket_domain_name = try(var.analytics_bucket_domain_name, "")
}