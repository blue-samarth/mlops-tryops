# GitHub Actions Variables (non-sensitive configuration)

resource "github_actions_variable" "aws_region" {
  repository    = var.github_repo
  variable_name = "AWS_REGION"
  value         = var.aws_region
}

resource "github_actions_variable" "environment" {
  repository    = var.github_repo
  variable_name = "ENVIRONMENT"
  value         = "production"
}

resource "github_actions_variable" "docker_buildkit" {
  repository    = var.github_repo
  variable_name = "DOCKER_BUILDKIT"
  value         = "1"
}