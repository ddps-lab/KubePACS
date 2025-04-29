provider "aws" {
  profile = var.awscli_profile
  region  = var.region
}

provider "aws" {
  profile = var.awscli_profile
  region  = "us-east-1"
  alias   = "virginia"
}


provider "helm" {
  kubernetes {
    host                   = module.eks.cluster_endpoint
    cluster_ca_certificate = base64decode(module.eks.cluster_certificate_authority_data)

    exec {
      api_version = "client.authentication.k8s.io/v1beta1"
      command     = "aws"
      args        = ["eks", "get-token", "--cluster-name", module.eks.cluster_name, "--profile", var.awscli_profile, "--region", var.region]
    }
  }
}
