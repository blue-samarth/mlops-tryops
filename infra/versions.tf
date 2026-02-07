terraform {
  required_version = "~> 1.13.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.27.0"
    }
    tls = {
      source  = "hashicorp/tls"
      version = "~> 4.2.1"
    }
    github = {
      source  = "integrations/github"
      version = "~> 6.6.0"
    }
  }
}

provider "aws" {
  region = "us-east-1"
}
