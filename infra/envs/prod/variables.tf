variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "acm_certificate_arn" {
  type = string
}

variable "api_domain_name" {
  type    = string
  default = ""
}

