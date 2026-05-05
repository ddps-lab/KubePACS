variable "cluster_name" {}
variable "oidc_provider_arn" {}
variable "prefix" {}
variable "region" {}
variable "cluster_endpoint" {}
variable "node_group_id" {}
variable "ecr_repository_url" {}

variable "controller_image_repository" {
  type    = string
  default = "ghcr.io/ddps-lab/kubepacs-karpenter-controller"
}

variable "controller_image_tag" {
  type    = string
  default = "1.8.1-kubepacs"
}

variable "controller_image_digest" {
  type    = string
  default = ""
}

variable "chart_path" {
  type    = string
  default = null
}

variable "kubepacs_enabled" {
  type    = bool
  default = true
}

variable "kubepacs_strategy_annotation" {
  type    = string
  default = "kubepacs.io/strategy"
}

variable "kubepacs_strategy_value" {
  type    = string
  default = "kubepacs"
}

variable "kubepacs_scenario_instance_label" {
  type    = string
  default = "kubepacs-scenario-instance"
}

variable "kubepacs_solver_path" {
  type    = string
  default = "/usr/local/bin/kubepacs_cli.py"
}

variable "kubepacs_nodeclass_enabled" {
  type    = bool
  default = true
}

variable "kubepacs_nodeclass_name" {
  type    = string
  default = "default"
}

variable "kubepacs_nodepool_enabled" {
  type    = bool
  default = true
}

variable "kubepacs_nodepool_name" {
  type    = string
  default = "default"
}

variable "kubepacs_verification_enabled" {
  type    = bool
  default = false
}
