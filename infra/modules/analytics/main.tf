# infra/modules/analytics/main.tf

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }
}

locals {
  bucket_name = "${var.name_prefix}-analytics-${var.aws_account_id}"

  # S3 STANDARD_IA requires transition >= 30 days.
  # Also expiration days must be > transition days.
  do_transition   = var.retention_days >= 31
  transition_days = 30
  expiration_days = var.retention_days
}

resource "aws_s3_bucket" "analytics" {
  bucket = local.bucket_name
}

resource "aws_s3_bucket_public_access_block" "analytics" {
  bucket                  = aws_s3_bucket.analytics.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# CloudFront legacy standard logs require ACLs to be enabled on the target bucket.
resource "aws_s3_bucket_ownership_controls" "analytics" {
  bucket = aws_s3_bucket.analytics.id
  rule {
    object_ownership = "BucketOwnerPreferred"
  }
}

# Explicit ACL policy with LogDelivery group grants
resource "aws_s3_bucket_acl" "analytics" {
  bucket = aws_s3_bucket.analytics.id

  access_control_policy {
    owner {
      id = data.aws_canonical_user_id.current.id
    }

    grant {
      grantee {
        type = "CanonicalUser"
        id   = data.aws_canonical_user_id.current.id
      }
      permission = "FULL_CONTROL"
    }

    # S3 Log Delivery group (used for delivery of access logs)
    grant {
      grantee {
        type = "Group"
        uri  = "http://acs.amazonaws.com/groups/s3/LogDelivery"
      }
      permission = "WRITE"
    }

    grant {
      grantee {
        type = "Group"
        uri  = "http://acs.amazonaws.com/groups/s3/LogDelivery"
      }
      permission = "READ_ACP"
    }
  }

  depends_on = [
    aws_s3_bucket_public_access_block.analytics,
    aws_s3_bucket_ownership_controls.analytics
  ]
}

data "aws_canonical_user_id" "current" {}

resource "aws_s3_bucket_server_side_encryption_configuration" "analytics" {
  bucket = aws_s3_bucket.analytics.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "analytics" {
  bucket = aws_s3_bucket.analytics.id

  rule {
    id     = "expire-cloudfront-logs"
    status = "Enabled"
    filter { prefix = "cloudfront/" }

    dynamic "transition" {
      for_each = local.do_transition ? [1] : []
      content {
        days          = local.transition_days
        storage_class = "STANDARD_IA"
      }
    }

    expiration { days = local.expiration_days }
  }

  rule {
    id     = "expire-apigw-logs-export"
    status = "Enabled"
    filter { prefix = "apigw/" }

    dynamic "transition" {
      for_each = local.do_transition ? [1] : []
      content {
        days          = local.transition_days
        storage_class = "STANDARD_IA"
      }
    }

    expiration { days = local.expiration_days }
  }

  rule {
    id     = "keep-rollups-longer"
    status = "Enabled"
    filter { prefix = "rollups/" }

    transition {
      days          = 60
      storage_class = "STANDARD_IA"
    }

    expiration { days = 730 }
  }
}

# Optional: if you still want your bucket policy gate
data "aws_iam_policy_document" "allow_cloudfront_logs" {
  count = var.enable_cloudfront_log_write ? 1 : 0

  statement {
    sid    = "AWSLogDeliveryWrite"
    effect = "Allow"

    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::${var.cloudfront_account_id}:root"]
    }

    actions   = ["s3:PutObject"]
    resources = ["arn:aws:s3:::${aws_s3_bucket.analytics.bucket}/cloudfront/*"]

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