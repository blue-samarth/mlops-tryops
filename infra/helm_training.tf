# Data source to get the latest training image from ECR by SHA tag
data "external" "training_latest_image" {
  program = ["bash", "-c", <<-EOT
    aws ecr describe-images \
      --repository-name ${aws_ecr_repository.training.name} \
      --region ${var.aws_region} \
      --query 'sort_by(imageDetails[?imageTags!=`null` && starts_with(imageTags[0], `sha-`)], &imagePushedAt)[-1]' \
      --output json | jq '{digest: .imageDigest}'
  EOT
  ]
}

# Training CronJob using Helm
resource "helm_release" "training" {
  name             = "mlops-training"
  chart            = "raw"
  repository       = "https://charts.helm.sh/incubator"
  namespace        = kubernetes_namespace_v1.namespace_mlops.metadata[0].name
  create_namespace = false
  version          = "0.2.5"
  wait             = false
  timeout          = 600
  atomic           = false

  values = [
    yamlencode({
      resources = [
        {
          apiVersion = "v1"
          kind       = "ServiceAccount"
          metadata = {
            name      = "training-service-account"
            namespace = kubernetes_namespace_v1.namespace_mlops.metadata[0].name
            annotations = { "eks.amazonaws.com/role-arn" = aws_iam_role.training_service_account.arn }
          }
        },
        {
          apiVersion = "v1"
          kind       = "ConfigMap"
          metadata = {
            name      = "training-config"
            namespace = kubernetes_namespace_v1.namespace_mlops.metadata[0].name
            labels = {
              "app.kubernetes.io/name"      = "mlops-training"
              "app.kubernetes.io/component" = "training"
            }
          }
          data = {
            S3_BUCKET   = aws_s3_bucket.models.id
            AWS_REGION  = var.aws_region
            ENVIRONMENT = var.environment
            LOG_LEVEL   = "INFO"
          }
        },
        {
          apiVersion = "batch/v1"
          kind       = "CronJob"
          metadata = {
            name      = "training"
            namespace = kubernetes_namespace_v1.namespace_mlops.metadata[0].name
            labels = {
              "app.kubernetes.io/name"      = "mlops-training"
              "app.kubernetes.io/component" = "training"
              "app.kubernetes.io/part-of"   = "mlops-platform"
              environment                   = var.environment
            }
          }
          spec = {
            schedule                   = "0 2 * * *"
            successfulJobsHistoryLimit = 3
            failedJobsHistoryLimit     = 1
            concurrencyPolicy          = "Forbid"
            jobTemplate = {
              spec = {
                backoffLimit = 2
                template = {
                  metadata = {
                    labels = {
                      "app.kubernetes.io/name"      = "mlops-training"
                      "app.kubernetes.io/component" = "training"
                      "app.kubernetes.io/part-of"   = "mlops-platform"
                      environment                   = var.environment
                    }
                  }
                  spec = {
                    serviceAccountName = "training-service-account"
                    restartPolicy      = "Never"
                    securityContext = {
                      runAsNonRoot = true
                      runAsUser    = 1000
                      fsGroup      = 1000
                    }
                    nodeSelector = {
                      workload = "training"
                      tier     = "batch"
                    }
                    tolerations = [
                      {
                        key      = "training"
                        operator = "Equal"
                        value    = "true"
                        effect   = "NoSchedule"
                      }
                    ]
                    containers = [
                      {
                        name            = "training"
                        image           = "${aws_ecr_repository.training.repository_url}@${data.external.training_latest_image.result.digest}"
                        imagePullPolicy = "IfNotPresent"
                        command         = ["/bin/sh"]
                        args = [ "-c",
                          "python scripts/generate_dummy_data.py --output data/training_data.csv --samples 5000 && python -m src.train.train --data data/training_data.csv --target approved"
                        ]
                        envFrom = [
                          {
                            configMapRef = { name = "training-config" }
                          }
                        ]
                        resources = {
                          requests = {
                            cpu    = "500m"
                            memory = "1Gi"
                          }
                          limits = {
                            cpu    = "1500m"
                            memory = "2Gi"
                          }
                        }
                      }
                    ]
                  }
                }
              }
            }
          }
        }
      ]
    })
  ]

  depends_on = [ aws_eks_node_group.training, aws_eks_addon.coredns, kubernetes_namespace_v1.namespace_mlops ]
}
