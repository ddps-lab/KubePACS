data "aws_ecrpublic_authorization_token" "token" {
  provider = aws.virginia
}

module "karpenter" {
  source  = "terraform-aws-modules/eks/aws//modules/karpenter"
  version = "20.37.2"

  cluster_name           = var.cluster_name
  enable_irsa            = true
  irsa_oidc_provider_arn = var.oidc_provider_arn
  iam_role_name          = "${var.prefix}-karpenter-controller-role"
  node_iam_role_name     = "${var.prefix}-karpenter-node-role"

  # Attach additional IAM policies to the Karpenter node IAM role
  node_iam_role_additional_policies = {
    AmazonSSMManagedInstanceCore = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
  }
}

resource "helm_release" "karpenter" {
  namespace           = "karpenter"
  create_namespace    = true
  name                = "karpenter"
  repository          = "oci://public.ecr.aws/karpenter"
  chart               = "karpenter"
  repository_username = data.aws_ecrpublic_authorization_token.token.user_name
  repository_password = data.aws_ecrpublic_authorization_token.token.password
  wait                = true
  version             = "1.4.0"

  values = [
    <<-EOT
    settings:
      clusterName: ${var.cluster_name}
      clusterEndpoint: ${var.cluster_endpoint}
      interruptionQueue: ${module.karpenter.queue_name}
    serviceAccount:
      annotations:
        eks.amazonaws.com/role-arn: ${module.karpenter.iam_role_arn}
    nodeSelector:
      eks.amazonaws.com/nodegroup: ${var.node_group_id}
    replicas: 1
    EOT
  ]

  depends_on = [module.karpenter]
}
