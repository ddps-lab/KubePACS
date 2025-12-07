module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "20.37.2"

  cluster_name    = "${var.prefix}-k8s-cluster"
  cluster_version = "1.33"

  cluster_endpoint_public_access = true

  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.public_subnets # Worker nodes can use all subnets

  # Filter subnets for control plane based on the last letter of the AZ name (a or b)
  control_plane_subnet_ids = [
    for i, subnet_id in module.vpc.public_subnets :
    subnet_id
    # Check if the last character of the AZ name is 'a' or 'b'
    if contains(["a", "b", "c"], substr(data.aws_availability_zones.available_az.names[i], -1, 1))
  ]

  eks_managed_node_group_defaults = {
    instance_types = ["t3.medium"]
  }

  eks_managed_node_groups = {
    kubepacs_addon_nodes = {
      vpc_security_group_ids = [module.eks.node_security_group_id, aws_security_group.worker_node_sg.id]
      ami_type               = "BOTTLEROCKET_x86_64"
      desired_size           = 1
      min_size               = 1
      max_size               = 2
    }
  }

  cluster_addons = {
    coredns                = {}
    eks-pod-identity-agent = {}
    kube-proxy             = {}
    vpc-cni                = {}
  }

  enable_cluster_creator_admin_permissions = true

  tags = {
    "karpenter.sh/discovery" = "${var.prefix}-k8s-cluster"
  }

  depends_on = [module.vpc]
}
