variable "env" {
  type = string
}

variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "name_prefix" {
  type    = string
  default = "llm-sre"
}

# Path to your lambda source folder (services/agent_api)
variable "lambda_src_dir" {
  type = string
}

# Optional: if you want CloudFront to call the API (we'll wire later)
variable "allowed_origins" {
  type    = list(string)
  default = []
}