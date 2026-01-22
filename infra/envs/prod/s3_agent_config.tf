data "aws_caller_identity" "current" {}

locals {
  agent_config_bucket = "llm-sre-config-prod-${data.aws_caller_identity.current.account_id}"
  agent_config_prefix = "agent-config"

  agent_config_agents_json     = "${path.root}/../../../config/agent-config/agents.json"
  agent_config_allowlists_json = "${path.root}/../../../config/agent-config/allowlists.json"
}

resource "aws_s3_bucket" "agent_config" {
  bucket = local.agent_config_bucket
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

resource "aws_s3_object" "agents_json" {
  bucket       = aws_s3_bucket.agent_config.id
  key          = "${local.agent_config_prefix}/agents.json"
  source       = local.agent_config_agents_json
  etag         = filemd5(local.agent_config_agents_json)
  content_type = "application/json"
}

resource "aws_s3_object" "allowlists_json" {
  bucket       = aws_s3_bucket.agent_config.id
  key          = "${local.agent_config_prefix}/allowlists.json"
  source       = local.agent_config_allowlists_json
  etag         = filemd5(local.agent_config_allowlists_json)
  content_type = "application/json"
}

output "agent_config_bucket" {
  value = aws_s3_bucket.agent_config.bucket
}