variable "awscli_profile" {
  default = "ddpslab"
}

variable "region" {
  default = "us-east-1"
}

variable "vpc_cidr" {
  type    = string
  default = "192.168.0.0/16"
}

variable "prefix" {
  type    = string
  default = "kubecaps-dev"
}

