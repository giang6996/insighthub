resource "aws_efs_file_system" "staging" {
  creation_token   = "${local.name_prefix}-staging"
  encrypted        = true
  performance_mode = "generalPurpose"
  throughput_mode  = "bursting"

  tags = {
    Name = "${local.name_prefix}-staging"
  }
}

resource "aws_efs_mount_target" "staging" {
  count = var.availability_zone_count

  file_system_id  = aws_efs_file_system.staging.id
  subnet_id       = aws_subnet.private[count.index].id
  security_groups = [aws_security_group.efs.id]
}

resource "aws_efs_access_point" "staging" {
  file_system_id = aws_efs_file_system.staging.id

  posix_user {
    gid = 1000
    uid = 1000
  }

  root_directory {
    path = "/staging"

    creation_info {
      owner_gid   = 1000
      owner_uid   = 1000
      permissions = "0750"
    }
  }

  tags = {
    Name = "${local.name_prefix}-staging-access-point"
  }
}
