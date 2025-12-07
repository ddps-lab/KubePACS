module "vpc" {
  source = "terraform-aws-modules/vpc/aws"

  name = "${var.prefix}-k8s-vpc"
  cidr = var.vpc_cidr

  azs             = data.aws_availability_zones.available_az.names
  public_subnets  = [for i, az in data.aws_availability_zones.available_az.names : cidrsubnet(var.vpc_cidr, 6, i)]
  map_public_ip_on_launch = true

  public_subnet_tags = {
    "kubernetes.io/cluster/${var.prefix}-k8s-cluster" = "shared"
    "kubernetes.io/role/elb" = "1"
    "karpenter.sh/discovery" = "${var.prefix}-k8s-cluster"
  }
}

resource "aws_security_group" "worker_node_sg" {
  ingress = [
  {
    cidr_blocks      = ["0.0.0.0/0"]
    description      = "allow all inbound"
    from_port        = 0
    to_port          = 0
    protocol         = "-1"
    ipv6_cidr_blocks = []
    prefix_list_ids  = []
    security_groups  = []
    self             = false
  }]

  egress = [{
    cidr_blocks      = ["0.0.0.0/0"]
    description      = "alow all outbound"
    from_port        = 0
    to_port          = 0
    protocol         = "-1"
    ipv6_cidr_blocks = []
    prefix_list_ids  = []
    security_groups  = []
    self             = false
  }]
  vpc_id = module.vpc.vpc_id

  tags = {
    "Name" = "${var.prefix}-worker-node-sg"
  }

  depends_on = [module.vpc]
}