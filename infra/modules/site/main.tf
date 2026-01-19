terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

data "aws_caller_identity" "current" {}

########################################
# Locals
########################################
locals {
  # Convert domains to safe bucket slugs
  domain_slug = {
    for d in var.domains :
    d => replace(replace(d, ".com", ""), ".", "-")
  }

  # Stable map for for_each keys
  domains_map = { for d in var.domains : d => d }
}

########################################
# CloudFront managed policies
########################################
data "aws_cloudfront_cache_policy" "caching_disabled" {
  name = "Managed-CachingDisabled"
}

data "aws_cloudfront_origin_request_policy" "all_viewer_except_host" {
  name = "Managed-AllViewerExceptHostHeader"
}

########################################
# S3 Buckets (Private)
########################################
resource "aws_s3_bucket" "site" {
  for_each = local.domains_map

  # IMPORTANT: wrap multiline ternary in parentheses so HCL parses it correctly
  bucket = (
    var.env == "prod"
    ? "s3-llm-sre-${local.domain_slug[each.key]}"
    : "s3-llm-sre-${var.env}-${replace(local.domain_slug[each.key], "${var.env}-", "")}"
  )

  tags = {
    Domain = each.key
  }
}

resource "aws_s3_bucket_public_access_block" "site" {
  for_each = aws_s3_bucket.site
  bucket   = each.value.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Upload placeholder content so CloudFront returns 200 (optional)
resource "aws_s3_object" "placeholder" {
  for_each     = var.enable_placeholder ? aws_s3_bucket.site : {}
  bucket       = each.value.id
  key          = "index.html"
  source       = "${path.module}/../../placeholder/index.html"
  etag         = filemd5("${path.module}/../../placeholder/index.html")
  content_type = "text/html"
}

########################################
# CloudFront OAC (recommended)
########################################
resource "aws_cloudfront_origin_access_control" "oac" {
  for_each                          = aws_s3_bucket.site
  name                              = "${each.key}-oac"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

########################################
# CloudFront distributions (one per domain)
########################################
resource "aws_cloudfront_distribution" "cdn" {
  for_each = aws_s3_bucket.site

  enabled             = true
  is_ipv6_enabled     = true
  comment             = "CDN for ${each.key}"
  default_root_object = "index.html"

  aliases = var.env == "prod" ? concat([each.key], ["www.${each.key}"]) : [each.key]

  # -----------------------
  # S3 origin (REST endpoint) + OAC
  # -----------------------
  origin {
    domain_name              = each.value.bucket_regional_domain_name
    origin_id                = "s3-${each.key}"
    origin_access_control_id = aws_cloudfront_origin_access_control.oac[each.key].id

    # IMPORTANT for OAC + S3 REST origins
    s3_origin_config {
      origin_access_identity = ""
    }
  }

  # -----------------------
  # API Gateway origin (/api/*) - optional
  # -----------------------
  dynamic "origin" {
    for_each = var.api_domain_name != "" ? [1] : []
    content {
      domain_name = var.api_domain_name
      origin_id   = "api-${each.key}"

      custom_origin_config {
        http_port              = 80
        https_port             = 443
        origin_protocol_policy = "https-only"
        origin_ssl_protocols   = ["TLSv1.2"]
      }
    }
  }

  # ============================================================
  # Static assets MUST NOT be rewritten to index.html
  # Keep this ordered behavior
  # ============================================================
  ordered_cache_behavior {
    path_pattern           = "/assets/*"
    target_origin_id       = "s3-${each.key}"
    viewer_protocol_policy = "redirect-to-https"

    allowed_methods = ["GET", "HEAD", "OPTIONS"]
    cached_methods  = ["GET", "HEAD", "OPTIONS"]

    compress = true

    forwarded_values {
      query_string = false
      cookies { forward = "none" }
    }
  }

  # -----------------------
  # Default (SPA pages)
  # -----------------------
  default_cache_behavior {
    target_origin_id       = "s3-${each.key}"
    viewer_protocol_policy = "redirect-to-https"

    allowed_methods = ["GET", "HEAD", "OPTIONS"]
    cached_methods  = ["GET", "HEAD", "OPTIONS"]

    compress = true

    forwarded_values {
      query_string = false
      cookies { forward = "none" }
    }
  }

  # -----------------------
  # Route /api/* to API Gateway - optional
  # -----------------------
  dynamic "ordered_cache_behavior" {
    for_each = var.api_domain_name != "" ? [1] : []
    content {
      path_pattern           = "/api/*"
      target_origin_id       = "api-${each.key}"
      viewer_protocol_policy = "redirect-to-https"

      allowed_methods = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
      cached_methods  = ["GET", "HEAD", "OPTIONS"]

      compress = true

      cache_policy_id          = data.aws_cloudfront_cache_policy.caching_disabled.id
      origin_request_policy_id = data.aws_cloudfront_origin_request_policy.all_viewer_except_host.id
    }
  }

  # ============================================================
  # SPA-friendly behavior: ONLY 404 → index.html
  # (Do NOT map 403 → index.html)
  # ============================================================
  custom_error_response {
    error_code            = 404
    response_code         = 200
    response_page_path    = "/index.html"
    error_caching_min_ttl = 0
  }

  restrictions {
    geo_restriction { restriction_type = "none" }
  }

  viewer_certificate {
    acm_certificate_arn      = var.acm_certificate_arn
    ssl_support_method       = "sni-only"
    minimum_protocol_version = "TLSv1.2_2021"
  }
}

########################################
# Bucket policy: allow ONLY CloudFront distribution to read objects
########################################
data "aws_iam_policy_document" "allow_cf_read" {
  for_each = aws_s3_bucket.site

  statement {
    sid       = "AllowCloudFrontReadOnly"
    actions   = ["s3:GetObject"]
    resources = ["${each.value.arn}/*"]

    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.cdn[each.key].arn]
    }
  }
}

resource "aws_s3_bucket_policy" "site" {
  for_each = aws_s3_bucket.site
  bucket   = each.value.id
  policy   = data.aws_iam_policy_document.allow_cf_read[each.key].json
}