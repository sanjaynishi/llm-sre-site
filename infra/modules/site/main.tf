# modules/site/main.tf
# Static UI hosting in S3 + CloudFront (OAC) + optional API origin (/api/*)
# + CloudFront access logs to a central analytics bucket (S3)

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }
}

locals {
  # Map of domain -> bucket name (you already standardized this style)
  # Example: aimlsre.com -> s3-llm-sre-aimlsre
  buckets = {
    for d, host in var.domains :
    d => "s3-${var.name_prefix}-${replace(replace(d, "www.", "www-"), ".", "-")}"
  }

  # Prefix for CloudFront logs per env
  cf_log_prefix = "cloudfront/${var.env}/"
}

# -----------------------------
# S3 buckets (one per domain)
# -----------------------------
resource "aws_s3_bucket" "site" {
  for_each = local.buckets
  bucket   = each.value
}

resource "aws_s3_bucket_public_access_block" "site" {
  for_each = aws_s3_bucket.site

  bucket                  = each.value.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "site" {
  for_each = aws_s3_bucket.site

  bucket = each.value.id
  versioning_configuration {
    status = "Enabled"
  }
}

# Optional placeholder index.html so CloudFront doesn't 403 before you sync UI
resource "aws_s3_object" "placeholder" {
  for_each = var.enable_placeholder ? aws_s3_bucket.site : {}

  bucket       = each.value.id
  key          = "index.html"
  content      = "<html><body><h1>${each.key}</h1><p>Placeholder</p></body></html>"
  content_type = "text/html"
}

# -----------------------------
# CloudFront Origin Access Control
# -----------------------------
resource "aws_cloudfront_origin_access_control" "oac" {
  for_each = aws_s3_bucket.site

  name                              = "${var.name_prefix}-${var.env}-${replace(each.key, ".", "-")}-oac"
  description                       = "OAC for ${each.key}"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# -----------------------------
# CloudFront distribution (one per domain)
# - default origin: S3 (UI)
# - optional api origin for /api/*
# - logs -> central analytics bucket
# -----------------------------
resource "aws_cloudfront_distribution" "cdn" {
  for_each = aws_s3_bucket.site

  enabled             = true
  is_ipv6_enabled     = true
  comment             = "${var.name_prefix}-${var.env} ${each.key}"
  default_root_object = "index.html"
  price_class         = "PriceClass_100"

  aliases = [each.key]

  viewer_certificate {
    acm_certificate_arn      = var.acm_certificate_arn
    ssl_support_method       = "sni-only"
    minimum_protocol_version = "TLSv1.2_2021"
  }

  # --- UI (S3) origin ---
  origin {
    domain_name              = "${each.value.bucket}.s3.${var.aws_region}.amazonaws.com"
    origin_id                = "s3-${each.key}"
    origin_access_control_id = aws_cloudfront_origin_access_control.oac[each.key].id

    s3_origin_config {}
  }

  # --- API origin (optional) ---
  dynamic "origin" {
    for_each = length(trimspace(var.api_domain_name)) > 0 ? [1] : []
    content {
      domain_name = var.api_domain_name
      origin_id   = "api-${each.key}"

      custom_origin_config {
        http_port              = 80
        https_port             = 443
        origin_protocol_policy = "https-only"
        origin_ssl_protocols   = ["TLSv1.2"]
        origin_read_timeout    = 30
        origin_keepalive_timeout = 5
      }
    }
  }

  default_cache_behavior {
    target_origin_id       = "s3-${each.key}"
    viewer_protocol_policy = "redirect-to-https"
    compress               = true

    allowed_methods = ["GET", "HEAD", "OPTIONS"]
    cached_methods  = ["GET", "HEAD", "OPTIONS"]

    forwarded_values {
      query_string = true
      cookies {
        forward = "none"
      }
    }
  }

  # Route /api/* to API Gateway host (if configured)
  dynamic "ordered_cache_behavior" {
    for_each = length(trimspace(var.api_domain_name)) > 0 ? [1] : []
    content {
      path_pattern           = "/api/*"
      target_origin_id       = "api-${each.key}"
      viewer_protocol_policy = "redirect-to-https"
      compress               = true

      allowed_methods = ["GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH", "DELETE"]
      cached_methods  = ["GET", "HEAD", "OPTIONS"]

      forwarded_values {
        query_string = true
        headers      = ["Authorization", "Content-Type", "Origin"]
        cookies {
          forward = "none"
        }
      }

      min_ttl     = 0
      default_ttl = 0
      max_ttl     = 0
    }
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  # ✅ CloudFront standard access logs (guard-railed: off if empty)
  dynamic "logging_config" {
    for_each = length(trimspace(var.analytics_bucket_domain_name)) > 0 ? [1] : []
    content {
      # MUST be bucket-domain-name (NOT bucket name)
      # example: llm-sre-analytics-830330555687.s3.amazonaws.com
      bucket          = var.analytics_bucket_domain_name
      include_cookies = false
      prefix          = local.cf_log_prefix
    }
  }
}

# -----------------------------
# Bucket policy: allow THIS CloudFront distribution to read objects (OAC)
# -----------------------------
data "aws_iam_policy_document" "allow_cf_read" {
  for_each = aws_s3_bucket.site

  statement {
    sid     = "AllowCloudFrontReadOnly"
    effect  = "Allow"
    actions = ["s3:GetObject"]

    resources = [
      "arn:aws:s3:::${each.value.bucket}/*"
    ]

    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values = [
        "arn:aws:cloudfront::${var.aws_account_id}:distribution/${aws_cloudfront_distribution.cdn[each.key].id}"
      ]
    }
  }
}

resource "aws_s3_bucket_policy" "site" {
  for_each = aws_s3_bucket.site

  bucket = each.value.id
  policy = data.aws_iam_policy_document.allow_cf_read[each.key].json
}