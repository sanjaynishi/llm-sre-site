terraform {
  backend "s3" {
    bucket         = "llm-sre-terraform-state-830330555687"
    key            = "llm-sre/aimlsre/dev/site/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "llm-sre-terraform-locks"
    encrypt        = true
  }
}