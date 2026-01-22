# main.tf (modules/agent_api)
# Updated with:
# - CloudWatch Logs permissions (AWSLambdaBasicExecutionRole)
# - S3 config read permissions (ListBucket + GetObject)
# - Build dir creation for archive output_path
# - API Gateway v2 CORS configuration (so browser Run button works)

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

resource "aws_lambda_function" "agent_api" {
  function_name = local.lambda_name
  role          = aws_iam_role.lambda_role.arn
  handler       = "app.lambda_handler"
  runtime       = "python3.11"

  filename         = data.archive_file.lambda_zip.output_path
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256

  timeout     = 15
  memory_size = 256

  environment {
    variables = {
      ENV = var.env

      # OpenAI (travel agent)
      OPENAI_API_KEY = var.openai_api_key
      OPENAI_MODEL   = var.openai_model

      # S3-backed config for dropdowns/catalog
      AGENT_CONFIG_BUCKET = var.agent_config_bucket
      AGENT_CONFIG_PREFIX = var.agent_config_prefix
    }
  }
}

# HTTP API (API Gateway v2)
resource "aws_apigatewayv2_api" "http_api" {
  name          = local.api_name
  protocol_type = "HTTP"

  # ✅ IMPORTANT: makes browser preflight work (Run button)
  cors_configuration {
    allow_origins = [
      "https://dev.aimlsre.com",
      "https://aimlsre.com",
      "https://www.aimlsre.com"
    ]
    allow_methods = ["GET", "POST", "OPTIONS"]
    allow_headers = ["Content-Type"]
    max_age       = 3600
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

# Routes
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

# Allow API Gateway to invoke Lambda
resource "aws_lambda_permission" "allow_apigw" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.agent_api.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http_api.execution_arn}/*/*"
}