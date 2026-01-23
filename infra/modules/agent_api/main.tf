# main.tf (modules/agent_api)
# Container-image Lambda + HTTP API (APIGW v2) + CORS + S3 read + Logs
# Notes:
# - For package_type="Image", DO NOT set runtime/handler/filename/source_code_hash.
# - ZIP/archive resources removed (not used for image Lambda).
# - VECTORS_PREFIX derived from var.s3_prefix to avoid hardcoding "knowledge/".

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
  ecr_repo_name = "${var.name_prefix}-agent-api-${var.env}" # keep consistent with lambda_name/pipeline
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

# CloudWatch Logs permissions
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

# ---------------- ECR Repo (for image) ----------------
# Keep this if Terraform should manage the repo. If the repo already exists,
# you may need `terraform import module.agent_api.aws_ecr_repository.agent_api <repo-name>`

resource "aws_ecr_repository" "agent_api" {
  name = local.ecr_repo_name
  image_scanning_configuration { scan_on_push = true }
}

resource "aws_ecr_lifecycle_policy" "agent_api" {
  repository = aws_ecr_repository.agent_api.name
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
  image_uri    = var.lambda_image_uri

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

      # Runbooks / vectors (same bucket)
      S3_BUCKET       = var.agent_config_bucket
      S3_PREFIX       = var.s3_prefix          # e.g. "knowledge/"
      RUNBOOKS_PREFIX = "runbooks/"            # resolves to "knowledge/runbooks/"
      AGENTS_KEY      = "agents.json"

      # RAG vector store
      VECTORS_PREFIX    = "${var.s3_prefix}vectors/dev/chroma/" # <- avoids hardcoding "knowledge/"
      CHROMA_COLLECTION = "runbooks_dev"
      EMBED_MODEL       = "text-embedding-3-small"
    }
  }

  depends_on = [
    aws_iam_role_policy_attachment.lambda_basic_logs,
    aws_iam_role_policy.lambda_s3_read_inline
  ]
}

# ---------------- API Gateway v2 (HTTP API) ----------------

resource "aws_apigatewayv2_api" "http_api" {
  name          = local.api_name
  protocol_type = "HTTP"

  cors_configuration {
    allow_origins = [
      "https://dev.aimlsre.com",
      "https://aimlsre.com",
      "https://www.aimlsre.com"
    ]
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

# ---------------- Routes ----------------
# Keep explicit routes you need + optional catch-all

resource "aws_apigatewayv2_route" "health" {
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "GET /api/health"
  target    = "integrations/${aws_apigatewayv2_integration.lambda_proxy.id}"
}

resource "aws_apigatewayv2_route" "agents" {
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "GET /api/agents"
  target    = "integrations/${aws_apigatewayv2_integration.lambda_proxy.id}"
}

resource "aws_apigatewayv2_route" "agent_run" {
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "POST /api/agent/run"
  target    = "integrations/${aws_apigatewayv2_integration.lambda_proxy.id}"
}

resource "aws_apigatewayv2_route" "runbooks_ask" {
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "POST /api/runbooks/ask"
  target    = "integrations/${aws_apigatewayv2_integration.lambda_proxy.id}"
}

# Optional routes (only keep if app.py implements these GET endpoints)
resource "aws_apigatewayv2_route" "runbooks" {
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "GET /api/runbooks"
  target    = "integrations/${aws_apigatewayv2_integration.lambda_proxy.id}"
}

resource "aws_apigatewayv2_route" "doc" {
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "GET /api/doc"
  target    = "integrations/${aws_apigatewayv2_integration.lambda_proxy.id}"
}

# Catch-all for future endpoints (safe with explicit routes)
resource "aws_apigatewayv2_route" "api_proxy" {
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "ANY /api/{proxy+}"
  target    = "integrations/${aws_apigatewayv2_integration.lambda_proxy.id}"
}

# Allow API Gateway to invoke Lambda
resource "aws_lambda_permission" "allow_apigw" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.agent_api.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http_api.execution_arn}/*/*"
}