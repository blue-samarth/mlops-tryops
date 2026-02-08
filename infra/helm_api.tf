# Data source to get the latest API image from ECR by SHA tag
data "external" "api_latest_image" {
  program = ["bash", "-c", <<-EOT
    aws ecr describe-images \
      --repository-name ${aws_ecr_repository.api.name} \
      --region ${var.aws_region} \
      --query 'sort_by(imageDetails[?imageTags!=`null` && starts_with(imageTags[0], `sha-`)], &imagePushedAt)[-1]' \
      --output json | jq '{digest: .imageDigest}'
  EOT
  ]
}

# API Deployment using Helm
resource "helm_release" "api" {
  name             = "mlops-api"
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
          kind       = "ConfigMap"
          metadata = {
            name      = "api-config"
            namespace = kubernetes_namespace_v1.namespace_mlops.metadata[0].name
            labels = {
              "app.kubernetes.io/name"      = "mlops-api"
              "app.kubernetes.io/component" = "api"
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
          apiVersion = "v1"
          kind       = "ServiceAccount"
          metadata = {
            name      = "api-service-account"
            namespace = kubernetes_namespace_v1.namespace_mlops.metadata[0].name
            annotations = {
              "eks.amazonaws.com/role-arn" = aws_iam_role.api_service_account.arn
            }
          }
        },
        {
          apiVersion = "apps/v1"
          kind       = "Deployment"
          metadata = {
            name      = "api"
            namespace = kubernetes_namespace_v1.namespace_mlops.metadata[0].name
            labels = {
              "app.kubernetes.io/name"      = "mlops-api"
              "app.kubernetes.io/component" = "api"
              "app.kubernetes.io/part-of"   = "mlops-platform"
              environment                   = var.environment
            }
          }
          spec = {
            replicas = 2
            selector = {
              matchLabels = {
                "app.kubernetes.io/name"      = "mlops-api"
                "app.kubernetes.io/component" = "api"
              }
            }
            template = {
              metadata = {
                labels = {
                  "app.kubernetes.io/name"      = "mlops-api"
                  "app.kubernetes.io/component" = "api"
                  "app.kubernetes.io/part-of"   = "mlops-platform"
                  environment                   = var.environment
                }
              }
              spec = {
                serviceAccountName = "api-service-account"
                securityContext = {
                  runAsNonRoot = true
                  runAsUser    = 1000
                  fsGroup      = 1000
                }
                nodeSelector = {
                  workload = "api"
                  tier     = "frontend"
                }
                containers = [
                  {
                    name            = "api"
                    image           = "${aws_ecr_repository.api.repository_url}@${data.external.api_latest_image.result.digest}"
                    imagePullPolicy = "IfNotPresent"
                    command         = ["python", "-m", "uvicorn"]
                    args            = ["src.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
                    ports = [
                      {
                        name          = "http"
                        containerPort = 8000
                        protocol      = "TCP"
                      }
                    ]
                    envFrom = [
                      {
                        configMapRef = { name = "api-config" }
                      }
                    ]
                    resources = {
                      requests = {
                        cpu    = "250m"
                        memory = "512Mi"
                      }
                      limits = {
                        cpu    = "1000m"
                        memory = "1Gi"
                      }
                    }
                    livenessProbe = {
                      httpGet = {
                        path = "/health"
                        port = 8000
                      }
                      initialDelaySeconds = 30
                      periodSeconds       = 10
                      timeoutSeconds      = 5
                      failureThreshold    = 3
                    }
                    readinessProbe = {
                      httpGet = {
                        path = "/health"
                        port = 8000
                      }
                      initialDelaySeconds = 10
                      periodSeconds       = 5
                      timeoutSeconds      = 3
                      failureThreshold    = 3
                    }
                  }
                ]
              }
            }
          }
        },
        {
          apiVersion = "v1"
          kind       = "Service"
          metadata = {
            name      = "api-service"
            namespace = kubernetes_namespace_v1.namespace_mlops.metadata[0].name
            labels = {
              "app.kubernetes.io/name"      = "mlops-api"
              "app.kubernetes.io/component" = "api"
            }
          }
          spec = {
            type = "LoadBalancer"
            selector = {
              "app.kubernetes.io/name"      = "mlops-api"
              "app.kubernetes.io/component" = "api"
            }
            ports = [
              {
                name       = "http"
                port       = 80
                targetPort = 8000
                protocol   = "TCP"
              }
            ]
          }
        },
        {
          apiVersion = "autoscaling/v2"
          kind       = "HorizontalPodAutoscaler"
          metadata = {
            name      = "api-hpa"
            namespace = kubernetes_namespace_v1.namespace_mlops.metadata[0].name
            labels = {
              "app.kubernetes.io/name"      = "mlops-api"
              "app.kubernetes.io/component" = "api"
            }
          }
          spec = {
            scaleTargetRef = {
              apiVersion = "apps/v1"
              kind       = "Deployment"
              name       = "api"
            }
            minReplicas = 2
            maxReplicas = 10
            metrics = [
              {
                type = "Resource"
                resource = {
                  name = "cpu"
                  target = {
                    type               = "Utilization"
                    averageUtilization = 70
                  }
                }
              },
              {
                type = "Resource"
                resource = {
                  name = "memory"
                  target = {
                    type               = "Utilization"
                    averageUtilization = 80
                  }
                }
              }
            ]
          }
        }
      ]
    })
  ]

  depends_on = [ aws_eks_node_group.api, aws_eks_addon.coredns, kubernetes_namespace_v1.namespace_mlops ]
}
