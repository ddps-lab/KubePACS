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

# Karpenter Controller 추가 권한 정책
resource "aws_iam_policy" "karpenter_controller_additional" {
  name        = "${var.prefix}-karpenter-controller-additional"
  description = "Additional permissions for Karpenter controller"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "iam:PassRole",
          "iam:ListInstanceProfiles",
          "iam:CreateInstanceProfile",
          "iam:TagInstanceProfile",
          "iam:AddRoleToInstanceProfile",
          "iam:RemoveRoleFromInstanceProfile",
          "iam:DeleteInstanceProfile",
          "iam:GetInstanceProfile",
          "ec2:DescribeInstanceTypes",
          "ec2:DescribeSpotPriceHistory"
        ]
        Resource = "*"
      }
    ]
  })
}

# 추가 정책을 Controller Role에 연결
resource "aws_iam_role_policy_attachment" "karpenter_controller_additional" {
  role       = module.karpenter.iam_role_name
  policy_arn = aws_iam_policy.karpenter_controller_additional.arn
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
    controller:
      image:
        repository: ${var.ecr_repository_url}
        tag: latest
      imagePullPolicy: Always
    EOT
  ]

  depends_on = [module.karpenter]
}
