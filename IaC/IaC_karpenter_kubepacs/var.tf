variable "awscli_profile" {
  default = "default"
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
  default = "kubepacs-e1"
}

variable "karpenter_chart_path" {
  type    = string
  default = null
}

variable "kubepacs_enabled" {
  type    = bool
  default = true
}

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
