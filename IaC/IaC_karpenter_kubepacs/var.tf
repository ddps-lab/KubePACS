variable "awscli_profile" {
  default = "default"
}

variable "region" {
  default = "ap-northeast-2"
}

variable "vpc_cidr" {
  type    = string
  default = "192.168.0.0/16"
}

variable "prefix" {
  type    = string
  default = "kubepacs-t1"
}

