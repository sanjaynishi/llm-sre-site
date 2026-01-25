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

  # S3 constraint for STANDARD_IA: transition days must be >= 30
  # Also, expiration must be > transition
  transition_days = max(30, var.retention_days)
  expiration_days = max(var.retention_days + 1, local.transition_days + 1)

  # AWS-published canonical ID for awslogsdelivery (CloudFront standard logs writer)
  # Source: CloudFront standard logging docs
  awslogsdelivery_canonical_id = "c4c1ede66af53448b93c283ce9448c4ba468c9432aa01d700d3878632f77d2d0"
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

# CloudFront standard logs REQUIRE ACLs to be enabled (NOT BucketOwnerEnforced)
resource "aws_s3_bucket_ownership_controls" "analytics" {
  bucket = aws_s3_bucket.analytics.id
  rule {
    object_ownership = "BucketOwnerPreferred"
  }
}

# Enable ACL capability + explicitly grant awslogsdelivery FULL_CONTROL
resource "aws_s3_bucket_acl" "analytics" {
  bucket = aws_s3_bucket.analytics.id

  access_control_policy {
    owner {
      id = data.aws_canonical_user_id.current.id
    }

    # Keep S3 LogDelivery group if you want (harmless)
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

    # ✅ REQUIRED: awslogsdelivery (CloudFront standard logs writer)
    grant {
      grantee {
        type = "CanonicalUser"
        id   = local.awslogsdelivery_canonical_id
      }
      permission = "FULL_CONTROL"
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

# ✅ Guard rails: expire raw logs; keep rollups longer
resource "aws_s3_bucket_lifecycle_configuration" "analytics" {
  bucket = aws_s3_bucket.analytics.id

  rule {
    id     = "expire-cloudfront-logs"
    status = "Enabled"
    filter { prefix = "cloudfront/" }

    transition {
      days          = local.transition_days
      storage_class = "STANDARD_IA"
    }

    expiration {
      days = local.expiration_days
    }
  }

  rule {
    id     = "expire-apigw-logs-export"
    status = "Enabled"
    filter { prefix = "apigw/" }

    transition {
      days          = local.transition_days
      storage_class = "STANDARD_IA"
    }

    expiration {
      days = local.expiration_days
    }
  }

  rule {
    id     = "keep-rollups-longer"
    status = "Enabled"
    filter { prefix = "rollups/" }

    transition {
      days          = 60
      storage_class = "STANDARD_IA"
    }

    expiration {
      days = 730
    }
  }
}

# Bucket policy (optional) – keep if you want extra guardrails; CloudFront relies on ACLs
data "aws_iam_policy_document" "allow_cloudfront_logs" {
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
  policy = data.aws_iam_policy_document.allow_cloudfront_logs.json
}