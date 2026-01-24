# modules/agent_api/main.tf
# Container-image Lambda + HTTP API (APIGW v2) + CORS + S3 read + Logs
#
# Fixes included:
# - Defines local.ecr_repo_name
# - Safe defaults for prefixes/collection
# - Optional ECR management (manage_ecr=true|false)
# - ECR repo protected from deletion (force_delete=false + prevent_destroy=true)
# - Guard against empty image_uri (clear error early)
# - One catch-all route (ANY /api/{proxy+}) since app routes internally

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

locals {
  api_name      = "${var.name_prefix}-agent-api-${var.env}"
  lambda_name   = "${var.name_prefix}-agent-api-${var.env}"
  ecr_repo_name = "${var.name_prefix}-agent-api-${var.env}"

  # Defaults that work across envs
  runbooks_prefix_effective   = length(trimspace(var.runbooks_prefix)) > 0 ? var.runbooks_prefix : "runbooks/"
  vectors_prefix_effective    = length(trimspace(var.vectors_prefix)) > 0 ? var.vectors_prefix : "${var.s3_prefix}vectors/${var.env}/chroma/"
  chroma_collection_effective = length(trimspace(var.chroma_collection)) > 0 ? var.chroma_collection : "runbooks_${var.env}"

  lambda_image_uri_effective = trimspace(var.lambda_image_uri)
}

# ---------------- IAM Role ----------------

resource "aws_iam_role" "lambda_role" {
  name = "${local.lambda_name}-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_basic_logs" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# S3 read permissions for config + vectors + runbooks (same bucket)
data "aws_iam_policy_document" "lambda_s3_read" {
  statement {
    sid       = "ListBucket"
    actions   = ["s3:ListBucket"]
    resources = ["arn:aws:s3:::${var.agent_config_bucket}"]
  }

  statement {
    sid       = "GetObjects"
    actions   = ["s3:GetObject"]
    resources = ["arn:aws:s3:::${var.agent_config_bucket}/*"]
  }
}

resource "aws_iam_role_policy" "lambda_s3_read_inline" {
  name   = "${local.lambda_name}-s3-read"
  role   = aws_iam_role.lambda_role.id
  policy = data.aws_iam_policy_document.lambda_s3_read.json
}

# ---------------- (Optional) ECR management ----------------
# If you want Terraform to manage ECR repo + lifecycle, set var.manage_ecr=true
resource "aws_ecr_repository" "agent_api" {
  count = var.manage_ecr ? 1 : 0

  name                 = local.ecr_repo_name
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  # ✅ Important: never delete the repo (avoids RepositoryNotEmptyException)
  force_delete = false

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_ecr_lifecycle_policy" "agent_api" {
  count = var.manage_ecr ? 1 : 0

  repository = aws_ecr_repository.agent_api[0].name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep last 20 images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 20
      }
      action = { type = "expire" }
    }]
  })
}

# ---------------- Lambda (container image) ----------------

resource "aws_lambda_function" "agent_api" {
  function_name = local.lambda_name
  role          = aws_iam_role.lambda_role.arn

  package_type = "Image"

  # MUST be set for Image Lambdas
  image_uri = local.lambda_image_uri_effective

  timeout     = 30
  memory_size = 512

  environment {
    variables = {
      ENV = var.env

      # OpenAI
      OPENAI_API_KEY = var.openai_api_key
      OPENAI_MODEL   = var.openai_model

      # S3-backed config for dropdowns/catalog
      AGENT_CONFIG_BUCKET = var.agent_config_bucket
      AGENT_CONFIG_PREFIX = var.agent_config_prefix
      AGENTS_KEY          = var.agents_key

      # Runbooks / vectors (same bucket)
      S3_BUCKET       = var.agent_config_bucket
      S3_PREFIX       = var.s3_prefix
      RUNBOOKS_PREFIX = local.runbooks_prefix_effective

      # RAG vector store
      VECTORS_PREFIX    = local.vectors_prefix_effective
      CHROMA_COLLECTION = local.chroma_collection_effective
      EMBED_MODEL       = var.embed_model
    }
  }

  depends_on = [
    aws_iam_role_policy_attachment.lambda_basic_logs,
    aws_iam_role_policy.lambda_s3_read_inline
  ]

  lifecycle {
    precondition {
      condition     = local.lambda_image_uri_effective != ""
      error_message = "lambda_image_uri must be non-empty for package_type=Image. Set TF_VAR_lambda_image_uri in CI (recommended) or in terraform.tfvars."
    }
  }
}

# ---------------- API Gateway v2 (HTTP API) ----------------

resource "aws_apigatewayv2_api" "http_api" {
  name          = local.api_name
  protocol_type = "HTTP"

  cors_configuration {
    allow_origins = var.cors_allow_origins
    allow_methods = ["GET", "POST", "OPTIONS"]
    allow_headers = [
      "Content-Type",
      "Authorization",
      "X-Requested-With",
      "X-Amz-Date",
      "X-Api-Key",
      "X-Amz-Security-Token"
    ]
    max_age = 3600
  }
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.http_api.id
  name        = "$default"
  auto_deploy = true
}

resource "aws_apigatewayv2_integration" "lambda_proxy" {
  api_id                 = aws_apigatewayv2_api.http_api.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.agent_api.invoke_arn
  payload_format_version = "2.0"
}

# One catch-all route; app routes internally
resource "aws_apigatewayv2_route" "api_proxy" {
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "ANY /api/{proxy+}"
  target    = "integrations/${aws_apigatewayv2_integration.lambda_proxy.id}"
}

resource "aws_lambda_permission" "allow_apigw" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.agent_api.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http_api.execution_arn}/*/*"
}