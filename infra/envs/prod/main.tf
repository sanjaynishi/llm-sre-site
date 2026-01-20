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
  env                 = "prod"

  domains = {
    "aimlsre.com"     = "aimlsre.com"
    "www.aimlsre.com" = "www.aimlsre.com"
  }

  # Optional (recommended to keep parity with dev)
  api_domain_name = "u4wqxay8bl.execute-api.us-east-1.amazonaws.com"
  #api_domain_name = var.api_domain_name
  enable_placeholder = true
}