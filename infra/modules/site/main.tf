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

########################################
# Locals
########################################
locals {
  # Convert domains to safe bucket slugs
  # sanjaynishi.com      -> sanjaynishi
  # dev.sanjaynishi.com  -> dev-sanjaynishi
  domain_slug = {
    for d in var.domains :
    d => replace(replace(d, ".com", ""), ".", "-")
  }
}

########################################
# S3 Buckets (Private)
########################################
resource "aws_s3_bucket" "site" {
  for_each = var.domains

  # PROD keeps existing bucket names (NO CHANGE)
  # DEV gets env-prefixed buckets
  bucket = var.env == "prod" ? "s3-llm-sre-${local.domain_slug[each.value]}" : "s3-llm-sre-${var.env}-${replace(local.domain_slug[each.value], "${var.env}-", "")}"

  tags = {
    Project = "llm-sre"
    Env     = var.env
    Domain  = each.value
    Owner   = "sanjay"
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

# Upload placeholder content so CloudFront returns 200
resource "aws_s3_object" "placeholder" {
  for_each     = aws_s3_bucket.site
  bucket       = each.value.id
  key          = "index.html"
  source       = "${path.module}/../../placeholder/index.html"
  etag         = filemd5("${path.module}/../../placeholder/index.html")
  content_type = "text/html"
}

# -----------------------
# CloudFront OAC (recommended)
# -----------------------
resource "aws_cloudfront_origin_access_control" "oac" {
  for_each                          = aws_s3_bucket.site
  name                              = "${each.key}-oac"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# -----------------------
# CloudFront distributions (one per domain)
# -----------------------
resource "aws_cloudfront_distribution" "cdn" {
  for_each = aws_s3_bucket.site

  enabled             = true
  is_ipv6_enabled     = true
  comment             = "CDN for ${each.key}"
  default_root_object = "index.html"

  # Apex only for now (as per your current plan)
  #aliases = [each.key]
  #aliases = [each.key, "www.${each.key}"]

 aliases = var.env == "prod" ? concat([each.key], ["www.${each.key}"]) : [each.key]

  origin {
    domain_name              = each.value.bucket_regional_domain_name
    origin_id                = "s3-${each.key}"
    origin_access_control_id = aws_cloudfront_origin_access_control.oac[each.key].id
  }

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

  # React SPA-friendly behavior: map 403/404 to index.html
  custom_error_response {
    error_code            = 403
    response_code         = 200
    response_page_path    = "/index.html"
    error_caching_min_ttl = 0
  }

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

# -----------------------
# Bucket policy: allow ONLY CloudFront distribution to read objects
# -----------------------
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