# Deploy React build output to S3 (one bucket per domain) using aws cli sync,
# and invalidate CloudFront so updates are visible immediately.
#
# Prereqs:
# - ui/ is built -> ui/dist exists
# - AWS CLI configured (AWS_PROFILE=llm-sre)
# - Terraform already manages aws_s3_bucket.site and aws_cloudfront_distribution.cdn

locals {
  # From infra/modules/site -> repo root -> ui/dist
  ui_dist_path = abspath("${path.module}/../../../ui/dist")
  ui_files     = fileset(local.ui_dist_path, "**")
}

# Optional: fail fast if UI isn't built
resource "null_resource" "assert_ui_built" {
  count = var.enable_tf_ui_deploy ? 1 : 0

  triggers = {
    ui_files_count = length(local.ui_files)
  }

  provisioner "local-exec" {
    command = "test ${length(local.ui_files)} -gt 0"
  }
}

resource "null_resource" "deploy_ui" {
  for_each = var.enable_tf_ui_deploy ? aws_s3_bucket.site : {}

  depends_on = [
    aws_s3_bucket_policy.site,
    null_resource.assert_ui_built
  ]

  triggers = {
    # Re-run deploy when build output changes
    ui_hash = sha1(join("", [
      for f in sort(fileset(local.ui_dist_path, "**")) :
      filemd5("${local.ui_dist_path}/${f}")
    ]))
    bucket = each.value.bucket
  }

  provisioner "local-exec" {
    command = "aws s3 sync \"${local.ui_dist_path}\" \"s3://${each.value.bucket}\" --delete --only-show-errors"
  }
}

resource "null_resource" "invalidate_cloudfront" {
  for_each = var.enable_tf_ui_deploy ? aws_cloudfront_distribution.cdn : {}

  triggers = {
    ui_hash = null_resource.deploy_ui[each.key].triggers.ui_hash
    dist_id = each.value.id
  }

  provisioner "local-exec" {
    command = "aws cloudfront create-invalidation --distribution-id ${each.value.id} --paths \"/*\""
  }

  depends_on = [null_resource.deploy_ui]
}