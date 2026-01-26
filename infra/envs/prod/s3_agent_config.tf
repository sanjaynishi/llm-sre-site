#data "aws_caller_identity" "current" {}

locals {
  # Unique per account + env
  agent_config_bucket_name = "llm-sre-agent-config-${var.env}-${data.aws_caller_identity.current.account_id}"

  # store under this prefix in the bucket
  agent_config_prefix = "agent-config"

  # repo_root/config/agent-config (because path.module is infra/envs/prod)
  agent_config_dir = "${path.module}/../../../config/agent-config"
}

resource "aws_s3_bucket" "agent_config" {
  bucket = local.agent_config_bucket_name
}

resource "aws_s3_bucket_public_access_block" "agent_config" {
  bucket                  = aws_s3_bucket.agent_config.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "agent_config" {
  bucket = aws_s3_bucket.agent_config.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "agent_config" {
  bucket = aws_s3_bucket.agent_config.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Upload the JSON files (these must exist locally)
resource "aws_s3_object" "agents_json" {
  bucket       = aws_s3_bucket.agent_config.id
  key          = "${local.agent_config_prefix}/agents.json"
  source       = "${local.agent_config_dir}/agents.json"
  content_type = "application/json"
  etag         = filemd5("${local.agent_config_dir}/agents.json")
}

resource "aws_s3_object" "allowlists_json" {
  bucket       = aws_s3_bucket.agent_config.id
  key          = "${local.agent_config_prefix}/allowlists.json"
  source       = "${local.agent_config_dir}/allowlists.json"
  content_type = "application/json"
  etag         = filemd5("${local.agent_config_dir}/allowlists.json")
}

