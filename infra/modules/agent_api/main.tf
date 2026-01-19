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

# Zip the lambda code (stdlib only)
data "archive_file" "lambda_zip" {
  type        = "zip"
  source_dir  = var.lambda_src_dir
  output_path = "${path.module}/build/${local.lambda_name}.zip"
}

resource "aws_iam_role" "lambda_role" {
  name = "${local.lambda_name}-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{
      Effect = "Allow",
      Principal = { Service = "lambda.amazonaws.com" },
      Action = "sts:AssumeRole"
    }]
  })
}

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
      # later: GEO_CACHE_TABLE, USAGE_TABLE, GPT limits, etc.
    }
  }
}

# HTTP API (API Gateway v2)
resource "aws_apigatewayv2_api" "http_api" {
  name          = local.api_name
  protocol_type = "HTTP"
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