resource "helm_release" "kyverno" {
  name             = "kyverno"
  repository       = "https://kyverno.github.io/kyverno/"
  chart            = "kyverno"
  namespace        = "kyverno"
  create_namespace = true
  version          = "3.2.6"
  wait             = true
  timeout          = 600

  set = [
    {
      name  = "admissionController.replicas"
      value = "2"
    },
    {
      name  = "backgroundController.replicas"
      value = "1"
    }
  ]

  depends_on = [ aws_eks_node_group.api, aws_eks_addon.coredns ]
}

# Kyverno policies using raw helm chart
resource "helm_release" "kyverno_policies" {
  name             = "kyverno-policies"
  chart            = "raw"
  repository       = "https://charts.helm.sh/incubator"
  namespace        = "kyverno"
  create_namespace = false
  version          = "0.2.5"

  values = [
    yamlencode({
      resources = [
        # ClusterPolicy: Verify image signatures with Cosign
        {
          apiVersion = "kyverno.io/v1"
          kind       = "ClusterPolicy"
          metadata = {
            name = "verify-image-signatures"
            annotations = {
              "policies.kyverno.io/title"       = "Verify Image Signatures"
              "policies.kyverno.io/category"    = "Security"
              "policies.kyverno.io/severity"    = "high"
              "policies.kyverno.io/subject"     = "Pod"
              "policies.kyverno.io/description" = "Verifies that all container images are signed with Cosign before deployment"
            }
          }
          spec = {
            validationFailureAction = "Enforce"
            background              = false
            webhookTimeoutSeconds   = 30
            failurePolicy           = "Fail"

            rules = [
              {
                name = "verify-api-image"
                match = {
                  any = [
                    {
                      resources = {
                        kinds = ["Pod"]
                        namespaces = [ kubernetes_namespace_v1.namespace_mlops.metadata[0].name ]
                        selector = {
                          matchLabels = { "app.kubernetes.io/component" = "api" }
                        }
                      }
                    }
                  ]
                }
                verifyImages = [
                  {
                    imageReferences = [ "${aws_ecr_repository.api.repository_url}:*" ]
                    attestors = [
                      {
                        entries = [
                          {
                            keyless = {
                              subject = "https://github.com/${var.github_org}/${var.github_repo}/.github/workflows/*"
                              issuer  = "https://token.actions.githubusercontent.com"
                              rekor = { url = "https://rekor.sigstore.dev" }
                            }
                          }
                        ]
                      }
                    ]
                  }
                ]
              },
              {
                name = "verify-training-image"
                match = {
                  any = [
                    {
                      resources = {
                        kinds = ["Pod"]
                        namespaces = [ kubernetes_namespace_v1.namespace_mlops.metadata[0].name ]
                        selector = {
                          matchLabels = { "app.kubernetes.io/component" = "training" }
                        }
                      }
                    }
                  ]
                }
                verifyImages = [
                  {
                    imageReferences = [ "${aws_ecr_repository.training.repository_url}:*" ]
                    attestors = [
                      {
                        entries = [
                          {
                            keyless = {
                              subject = "https://github.com/${var.github_org}/${var.github_repo}/.github/workflows/*"
                              issuer  = "https://token.actions.githubusercontent.com"
                              rekor = { url = "https://rekor.sigstore.dev" }
                            }
                          }
                        ]
                      }
                    ]
                  }
                ]
              }
            ]
          }
        },
        # ClusterPolicy: Require non-root containers
        {
          apiVersion = "kyverno.io/v1"
          kind       = "ClusterPolicy"
          metadata = {
            name = "require-non-root"
            annotations = {
              "policies.kyverno.io/title"       = "Require Non-Root Containers"
              "policies.kyverno.io/category"    = "Security"
              "policies.kyverno.io/severity"    = "high"
              "policies.kyverno.io/description" = "Ensures containers run as non-root user"
            }
          }
          spec = {
            validationFailureAction = "Enforce"
            background              = true

            rules = [
              {
                name = "check-runAsNonRoot"
                match = {
                  any = [
                    {
                      resources = {
                        kinds = ["Pod"]
                        namespaces = [ kubernetes_namespace_v1.namespace_mlops.metadata[0].name ]
                      }
                    }
                  ]
                }
                validate = {
                  message = "Running as root is not allowed. Set runAsNonRoot to true in securityContext."
                  pattern = {
                    spec = {
                      securityContext = { runAsNonRoot = true }
                    }
                  }
                }
              }
            ]
          }
        },
        # ClusterPolicy: Disallow privileged containers
        {
          apiVersion = "kyverno.io/v1"
          kind       = "ClusterPolicy"
          metadata = {
            name = "disallow-privileged-containers"
            annotations = {
              "policies.kyverno.io/title"       = "Disallow Privileged Containers"
              "policies.kyverno.io/category"    = "Security"
              "policies.kyverno.io/severity"    = "critical"
              "policies.kyverno.io/description" = "Prevents deployment of privileged containers"
            }
          }
          spec = {
            validationFailureAction = "Enforce"
            background              = true

            rules = [
              {
                name = "check-privileged"
                match = {
                  any = [
                    {
                      resources = {
                        kinds = ["Pod"]
                        namespaces = [ kubernetes_namespace_v1.namespace_mlops.metadata[0].name ]
                      }
                    }
                  ]
                }
                validate = {
                  message = "Privileged containers are not allowed."
                  pattern = {
                    spec = {
                      containers = [
                        {
                          "(securityContext)" = { "(privileged)" = false }
                        }
                      ]
                    }
                  }
                }
              }
            ]
          }
        },
        # ClusterPolicy: Require resource limits
        {
          apiVersion = "kyverno.io/v1"
          kind       = "ClusterPolicy"
          metadata = {
            name = "require-resource-limits"
            annotations = {
              "policies.kyverno.io/title"       = "Require Resource Limits"
              "policies.kyverno.io/category"    = "Best Practices"
              "policies.kyverno.io/severity"    = "medium"
              "policies.kyverno.io/description" = "Ensures all containers have resource requests and limits defined"
            }
          }
          spec = {
            validationFailureAction = "Enforce"
            background              = true

            rules = [
              {
                name = "check-resources"
                match = {
                  any = [
                    {
                      resources = {
                        kinds = ["Pod"]
                        namespaces = [ kubernetes_namespace_v1.namespace_mlops.metadata[0].name ]
                      }
                    }
                  ]
                }
                validate = {
                  message = "All containers must have CPU and memory requests and limits defined."
                  pattern = {
                    spec = {
                      containers = [
                        {
                          resources = {
                            requests = {
                              cpu    = "?*"
                              memory = "?*"
                            }
                            limits = {
                              cpu    = "?*"
                              memory = "?*"
                            }
                          }
                        }
                      ]
                    }
                  }
                }
              }
            ]
          }
        }
      ]
    })
  ]

  depends_on = [helm_release.kyverno]
}
