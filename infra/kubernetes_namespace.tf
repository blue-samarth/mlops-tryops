# Kubernetes namespace for MLOps (shared)
resource "kubernetes_namespace_v1" "namespace_mlops" {
  metadata {
    name = "mlops"
    labels = {
      name        = "mlops"
      environment = local.environment
      managed-by  = "terraform"
    }
  }

  depends_on = [ aws_eks_node_group.api, aws_eks_node_group.training, aws_eks_addon.coredns ]
}
