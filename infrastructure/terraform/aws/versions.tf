terraform {
  required_version = ">= 1.9"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.80"
    }
  }

  # Keep state out of the repository. Example remote backend:
  # backend "s3" {
  #   bucket       = "your-terraform-state-bucket"
  #   key          = "cloudpulse/terraform.tfstate"
  #   region       = "me-central-1"
  #   use_lockfile = true
  #   encrypt      = true
  # }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project     = "cloudpulse"
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}
