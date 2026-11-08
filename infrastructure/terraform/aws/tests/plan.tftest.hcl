# Runs without an AWS account: the provider is mocked, so nothing is created and no credentials are used.
mock_provider "aws" {
  override_data {
    target = data.aws_availability_zones.available
    values = { names = ["az-a", "az-b", "az-c"] }
  }
}

run "defaults_are_private_and_encrypted" {
  command = plan

  assert {
    condition     = aws_db_instance.this.publicly_accessible == false
    error_message = "The database must not be public."
  }
  assert {
    condition     = aws_db_instance.this.storage_encrypted == true
    error_message = "Database storage must be encrypted."
  }
  assert {
    condition     = aws_db_instance.this.manage_master_user_password == true
    error_message = "The database password must be managed by RDS, not stored in Terraform."
  }
  assert {
    condition     = aws_eks_cluster.this.vpc_config[0].endpoint_public_access == false
    error_message = "The Kubernetes API must be private unless networks are listed."
  }
  assert {
    condition     = aws_vpc_security_group_ingress_rule.database_from_cluster.cidr_ipv4 == null
    error_message = "Database access must come from the cluster security group, not an address range."
  }
  assert {
    condition     = length(aws_subnet.private) == 2 && aws_subnet.private[0].availability_zone != aws_subnet.private[1].availability_zone
    error_message = "Private subnets must span two availability zones."
  }
  assert {
    condition     = alltrue([for repo in aws_ecr_repository.images : repo.image_tag_mutability == "IMMUTABLE"])
    error_message = "Image tags must be immutable."
  }
}

run "public_api_is_limited_to_listed_networks" {
  command = plan

  variables {
    api_public_cidrs = ["203.0.113.10/32"]
  }

  assert {
    condition     = aws_eks_cluster.this.vpc_config[0].endpoint_public_access == true
    error_message = "Listing a network should enable the public endpoint."
  }
  assert {
    condition     = contains(aws_eks_cluster.this.vpc_config[0].public_access_cidrs, "203.0.113.10/32")
    error_message = "Only the listed network should be allowed."
  }
}

run "rejects_an_api_open_to_the_internet" {
  command = plan

  variables {
    api_public_cidrs = ["0.0.0.0/0"]
  }

  expect_failures = [var.api_public_cidrs]
}

run "rejects_an_invalid_environment_name" {
  command = plan

  variables {
    environment = "Bad Name"
  }

  expect_failures = [var.environment]
}
