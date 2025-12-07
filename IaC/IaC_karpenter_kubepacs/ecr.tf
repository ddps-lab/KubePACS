resource "aws_ecr_repository" "karpenter" {
  name                 = "karpenter-custom"
  image_tag_mutability = "MUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }
}

output "ecr_repository_url" {
  value = aws_ecr_repository.karpenter.repository_url
}
