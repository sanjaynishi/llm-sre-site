resource "aws_iam_role_policy" "agent_api_s3_config_read" {
  name = "${local.lambda_name}-s3-config-read"
  role = aws_iam_role.lambda_role.name

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect = "Allow",
        Action = ["s3:GetObject"],
        Resource = [
          "arn:aws:s3:::${var.agent_config_bucket}/${var.agent_config_prefix}/*"
        ]
      }
    ]
  })
}