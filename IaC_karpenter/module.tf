module "karpenter" {
  source            = "./karpenter"
  prefix            = var.prefix
  oidc_provider_arn = module.eks.oidc_provider_arn
  node_group_id     = split(":", module.eks.eks_managed_node_groups.addon_nodes.node_group_id)[1]
  cluster_name      = module.eks.cluster_name
  cluster_endpoint  = module.eks.cluster_endpoint

  providers = {
    aws          = aws
    aws.virginia = aws.virginia
  }
  depends_on = [module.eks]
}
