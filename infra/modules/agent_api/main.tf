# main.tf (modules/agent_api)
# Updated with:
# - CloudWatch Logs permissions (AWSLambdaBasicExecutionRole)
# - S3 read permissions for runbooks/config (ListBucket + GetObject)
# - Build dir creation for archive output_path
# - API Gateway v2 CORS configuration (browser-friendly)
# - Added routes for /api/health, /api/runbooks, /api/doc
# - Optional catch-all route ANY /api/{proxy+} for future endpoints

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.4"
    }
  }
}

locals {
  api_name    = "${var.name_prefix}-agent-api-${var.env}"
  lambda_name = "${var.name_prefix}-agent-api-${var.env}"
}

# Ensure build dir exists for zip output
resource "null_resource" "build_dir" {
  provisioner "local-exec" {
    command = "mkdir -p ${path.module}/build"
  }
}

# Zip the lambda code (stdlib only, plus whatever you vendor/package)
data "archive_file" "lambda_zip" {
  depends_on  = [null_resource.build_dir]
  type        = "zip"
  source_dir  = var.lambda_src_dir
  output_path = "${path.module}/build/${local.lambda_name}.zip"
}

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

# ✅ REQUIRED: CloudWatch Logs permissions for Lambda
resource "aws_iam_role_policy_attachment" "lambda_basic_logs" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# ✅ REQUIRED: S3 read permissions for runbooks + agents.json
# Notes:
# - ListBucket must be granted on the bucket ARN.
# - GetObject must be granted on bucket/*.
data "aws_iam_policy_document" "lambda_s3_read" {
  statement {
    sid     = "ListBucket"
    actions = ["s3:ListBucket"]
    resources = [
      "arn:aws:s3:::${var.agent_config_bucket}"
    ]
  }

  statement {
    sid     = "GetObjects"
    actions = ["s3:GetObject"]
    resources = [
      "arn:aws:s3:::${var.agent_config_bucket}/*"
    ]
  }
}

# ✅ Inline policy (no iam:CreatePolicy needed)
resource "aws_iam_role_policy" "lambda_s3_read_inline" {
  name   = "${local.lambda_name}-s3-read"
  role   = aws_iam_role.lambda_role.id
  policy = data.aws_iam_policy_document.lambda_s3_read.json
}

resource "aws_lambda_function" "agent_api" {
  function_name = local.lambda_name
  role          = aws_iam_role.lambda_role.arn

  # ⚠️ IMPORTANT:
  # If your python file has: def lambda_handler(event, context): -> keep as below
  # If your python file has: def handler(event, context):        -> change to "app.handler"
  handler = "app.lambda_handler"
  runtime = "python3.11"

  filename         = data.archive_file.lambda_zip.output_path
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256

  timeout     = 15
  memory_size = 256

  environment {
    variables = {
      ENV = var.env

      # OpenAI
      OPENAI_API_KEY = var.openai_api_key
      OPENAI_MODEL   = var.openai_model

      # S3-backed config for dropdowns/catalog (existing)
      AGENT_CONFIG_BUCKET = var.agent_config_bucket
      AGENT_CONFIG_PREFIX = var.agent_config_prefix

      # Runbooks / docs (new)
      # Your uploaded runbooks are under:
      # s3://llm-sre-agent-config-dev-830330555687/knowledge/runbooks/*.pdf
      S3_BUCKET       = var.agent_config_bucket
      S3_PREFIX       = var.s3_prefix          # e.g. "knowledge/"
      RUNBOOKS_PREFIX = "runbooks/"            # resolves to "knowledge/runbooks/"
      AGENTS_KEY      = "agents.json"

      VECTORS_PREFIX    = "knowledge/vectors/dev/chroma/"
      CHROMA_COLLECTION = "runbooks_dev"
      EMBED_MODEL       = "text-embedding-3-small"
    }
  }
}

resource "aws_ecr_repository" "agent_api" {
  name = "${local.lambda_name}"
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


# HTTP API (API Gateway v2)
resource "aws_apigatewayv2_api" "http_api" {
  name          = local.api_name
  protocol_type = "HTTP"

  # ✅ IMPORTANT: makes browser preflight work
  # Allow headers beyond Content-Type (Authorization, etc.)
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

# Integrate API -> Lambda (proxy)
resource "aws_apigatewayv2_integration" "lambda_proxy" {
  api_id                 = aws_apigatewayv2_api.http_api.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.agent_api.invoke_arn
  payload_format_version = "2.0"
}

# Routes (explicit)
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

# ✅ New: runbook endpoints (match the Lambda you added)
resource "aws_apigatewayv2_route" "health" {
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "GET /api/health"
  target    = "integrations/${aws_apigatewayv2_integration.lambda_proxy.id}"
}

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

# ✅ Optional: catch-all route so you don't keep adding new routes
# You can keep this enabled; it won't break explicit routes.
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

resource "aws_apigatewayv2_route" "runbooks_ask" {
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "POST /api/runbooks/ask"
  target    = "integrations/${aws_apigatewayv2_integration.lambda_proxy.id}"
}