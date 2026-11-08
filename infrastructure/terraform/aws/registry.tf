resource "aws_ecr_repository" "images" {
  for_each = toset(["api", "web"])

  name                 = "cloudpulse/${each.key}"
  image_tag_mutability = "IMMUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }
}
