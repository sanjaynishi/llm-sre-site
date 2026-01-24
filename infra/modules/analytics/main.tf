# modules/analytics/main.tf
# Central analytics S3 bucket for CloudFront (and future API) logs
# Guardrails included:
# - No public access
# - SSE encryption
# - Versioning
# - Lifecycle retention (expire raw logs)
# - Optional CloudFront log-delivery bucket policy (toggleable)

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }
}

data "aws_caller_identity" "current" {}

locals {
  bucket_name = "llm-sre-analytics-${data.aws_caller_identity.current.account_id}"
}

# -----------------------------
# S3 bucket (analytics)
# -----------------------------
resource "aws_s3_bucket" "analytics" {
  bucket = local.bucket_name

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_public_access_block" "analytics" {
  bucket                  = aws_s3_bucket.analytics.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "analytics" {
  bucket = aws_s3_bucket.analytics.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "analytics" {
  bucket = aws_s3_bucket.analytics.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# -----------------------------
# Lifecycle guardrails
# - expire raw logs (cost control)
# - keep rollups longer
# -----------------------------
resource "aws_s3_bucket_lifecycle_configuration" "analytics" {
  bucket = aws_s3_bucket.analytics.id

  rule {
    id     = "expire-cloudfront-logs"
    status = "Enabled"
    filter { prefix = "cloudfront/" }

    transition {
      days          = 30
      storage_class = "STANDARD_IA"
    }

    expiration { days = 90 }
  }

  rule {
    id     = "expire-api-logs"
    status = "Enabled"
    filter { prefix = "apigw/" }

    transition {
      days          = 30
      storage_class = "STANDARD_IA"
    }

    expiration { days = 90 }
  }

  rule {
    id     = "keep-rollups-longer"
    status = "Enabled"
    filter { prefix = "rollups/" }

    transition {
      days          = 60
      storage_class = "STANDARD_IA"
    }

    expiration { days = 730 } # 2 years
  }
}

# -----------------------------
# Optional: allow CloudFront standard logs to write to this bucket
# CloudFront standard logs require ACL bucket-owner-full-control.
# This is guarded by var.enable_cloudfront_log_write.
# -----------------------------
data "aws_iam_policy_document" "allow_cloudfront_logs" {
  count = var.enable_cloudfront_log_write ? 1 : 0

  statement {
    sid    = "AWSLogDeliveryWrite"
    effect = "Allow"

    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::${var.cloudfront_account_id}:root"]
    }

    actions = ["s3:PutObject"]

    resources = [
      "arn:aws:s3:::${aws_s3_bucket.analytics.bucket}/cloudfront/*"
    ]

    condition {
      test     = "StringEquals"
      variable = "s3:x-amz-acl"
      values   = ["bucket-owner-full-control"]
    }
  }

  statement {
    sid    = "AWSLogDeliveryAclCheck"
    effect = "Allow"

    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::${var.cloudfront_account_id}:root"]
    }

    actions   = ["s3:GetBucketAcl"]
    resources = [aws_s3_bucket.analytics.arn]
  }
}

resource "aws_s3_bucket_policy" "analytics" {
  count  = var.enable_cloudfront_log_write ? 1 : 0
  bucket = aws_s3_bucket.analytics.id
  policy = data.aws_iam_policy_document.allow_cloudfront_logs[0].json
}