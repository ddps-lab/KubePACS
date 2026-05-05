module "karpenter" {
  source             = "./karpenter"
  prefix             = var.prefix
  region             = var.region
  oidc_provider_arn  = module.eks.oidc_provider_arn
  node_group_id      = split(":", module.eks.eks_managed_node_groups.kubepacs_addon_nodes.node_group_id)[1]
  cluster_name       = module.eks.cluster_name
  cluster_endpoint   = module.eks.cluster_endpoint
  ecr_repository_url = aws_ecr_repository.karpenter.repository_url

  controller_image_repository = var.controller_image_repository
  controller_image_tag        = var.controller_image_tag
  controller_image_digest     = var.controller_image_digest

  chart_path                       = var.karpenter_chart_path
  kubepacs_enabled                 = var.kubepacs_enabled
  kubepacs_strategy_annotation     = var.kubepacs_strategy_annotation
  kubepacs_strategy_value          = var.kubepacs_strategy_value
  kubepacs_scenario_instance_label = var.kubepacs_scenario_instance_label
  kubepacs_solver_path             = var.kubepacs_solver_path
  kubepacs_nodeclass_enabled       = var.kubepacs_nodeclass_enabled
  kubepacs_nodeclass_name          = var.kubepacs_nodeclass_name
  kubepacs_nodepool_enabled        = var.kubepacs_nodepool_enabled
  kubepacs_nodepool_name           = var.kubepacs_nodepool_name
  kubepacs_verification_enabled    = var.kubepacs_verification_enabled

  depends_on = [module.eks]
}
