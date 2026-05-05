locals {
  karpenter_chart_path = coalesce(
    var.chart_path,
    abspath("${path.module}/../../../KubePACS_with_Karpenter/karpenter-provider-aws/charts/karpenter"),
  )
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
  namespace        = "karpenter"
  create_namespace = true
  name             = "karpenter"
  chart            = local.karpenter_chart_path
  wait             = true

  values = [
    <<-EOT
    imagePullPolicy: Always
    settings:
      clusterName: ${var.cluster_name}
      clusterEndpoint: ${var.cluster_endpoint}
      interruptionQueue: ${module.karpenter.queue_name}
      kubepacs:
        enabled: ${var.kubepacs_enabled}
        strategyAnnotation: ${var.kubepacs_strategy_annotation}
        strategyValue: ${var.kubepacs_strategy_value}
        scenarioInstanceLabel: ${var.kubepacs_scenario_instance_label}
        solverPath: ${var.kubepacs_solver_path}
    serviceAccount:
      annotations:
        eks.amazonaws.com/role-arn: ${module.karpenter.iam_role_arn}
    nodeSelector:
      eks.amazonaws.com/nodegroup: ${var.node_group_id}
    replicas: 1
    controller:
      image:
        repository: ${var.controller_image_repository}
        tag: ${var.controller_image_tag}
        digest: "${var.controller_image_digest}"
      env:
        - name: AWS_REGION
          value: ${var.region}
      extraVolumeMounts:
        - name: tmp
          mountPath: /tmp
    extraVolumes:
      - name: tmp
        emptyDir: {}
    kubepacsNodeClass:
      enabled: ${var.kubepacs_nodeclass_enabled}
      name: ${var.kubepacs_nodeclass_name}
      role: ${module.karpenter.node_iam_role_name}
      subnetSelectorTerms:
        - tags:
            karpenter.sh/discovery: ${var.cluster_name}
      securityGroupSelectorTerms:
        - tags:
            karpenter.sh/discovery: ${var.cluster_name}
      amiSelectorTerms:
        - alias: al2023@latest
    kubepacsNodePool:
      enabled: ${var.kubepacs_nodepool_enabled}
      name: ${var.kubepacs_nodepool_name}
      nodeClassRef:
        group: karpenter.k8s.aws
        kind: EC2NodeClass
        name: ${var.kubepacs_nodeclass_name}
    kubepacsVerification:
      enabled: ${var.kubepacs_verification_enabled}
    EOT
  ]

  depends_on = [module.karpenter]
}
