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

module "site" {
  source              = "../../modules/site"
  aws_region          = var.aws_region
  acm_certificate_arn = var.acm_certificate_arn
  env                 = "dev"

  enable_placeholder = false # 👈 THIS IS THE FIX
  # 👇 ADD THIS LINE
  api_domain_name = replace(replace(module.agent_api.http_api_endpoint, "https://", ""), "/", "")

  domains = {
    "dev.aimlsre.com" = "dev.aimlsre.com"
  }

}

module "agent_api" {
  source = "../../modules/agent_api"
  
  openai_api_key = var.openai_api_key
  openai_model   = "gpt-4o-mini"
  env        = var.env
  aws_region = var.aws_region
  

  # IMPORTANT: path from infra/envs/dev -> repo_root/services/agent_api
  lambda_src_dir = "${path.module}/../../../services/agent_api"
}

