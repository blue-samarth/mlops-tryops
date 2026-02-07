# GitHub Secrets Management Module Integration

# Run PAT script only once (if .github_pat_store doesn't exist)
resource "terraform_data" "github_pat_setup" {
  triggers_replace = {
    # Only run if PAT store file doesn't exist
    pat_missing = fileexists("${path.module}/github_infra/.github_pat_store") ? "exists" : "missing"
  }

  provisioner "local-exec" {
    when    = create
    command = <<-EOT
      if [ ! -f "${path.module}/github_infra/.github_pat_store" ]; then
        echo "Setting up GitHub PAT..."
        cd ${path.module}/github_infra
        chmod +x github_pat_script.sh
        ./github_pat_script.sh -o ${local.github_org} -r ${local.github_repo}
      else
        echo "GitHub PAT already exists, skipping setup"
      fi
    EOT
  }
}

# Read the PAT from the stored file
data "local_file" "github_pat" {
  filename = "${path.module}/github_infra/.github_pat_store"

  depends_on = [terraform_data.github_pat_setup]
}

# Parse PAT from store file (plain text format)
locals {
  github_pat = trimspace(data.local_file.github_pat.content)
}

# Configure GitHub provider
provider "github" {
  owner = local.github_org
  token = local.github_pat
}

# Call GitHub Infra module to create secrets
module "github_secrets" {
  source = "./github_infra"

  providers = {
    github = github
  }

  # GitHub configuration
  github_personal_access_token = local.github_pat
  github_owner                 = local.github_org
  github_repo                  = local.github_repo

  # AWS outputs to pass as secrets
  aws_role_arn                = aws_iam_role.github_actions_ecr.arn
  ecr_api_repository_url      = aws_ecr_repository.api.repository_url
  ecr_training_repository_url = aws_ecr_repository.training.repository_url
  aws_region                  = local.aws_region
  models_bucket_name          = aws_s3_bucket.models.id
}

# Output the secrets that were created
output "github_secrets_created" {
  description = "List of GitHub secrets that were created"
  value       = module.github_secrets.secrets_created
}

output "github_repository" {
  description = "GitHub repository where secrets were created"
  value       = module.github_secrets.repository_full_name
}
