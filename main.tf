# Terraform Configuration for Greeks Collector AWS Infrastructure
# This creates a cost-effective setup within your $100 budget

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# Configure AWS Provider - Update region as needed
provider "aws" {
  region = "ap-south-1"  # Mumbai - closest to NSE
}

# Variables
variable "instance_type" {
  default = "t3.small"  # ~$15/month - sufficient for this workload
  # t3.micro  = ~$7.5/month (might be tight on memory)
  # t3.small  = ~$15/month  (recommended)
  # t3.medium = ~$30/month  (comfortable headroom)
}

variable "db_instance_type" {
  default = "db.t3.micro"  # ~$12/month for RDS
}

variable "project_name" {
  default = "greeks-collector"
}

# VPC and Networking (using default VPC for simplicity)
data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

# Security Group for EC2
resource "aws_security_group" "ec2_sg" {
  name        = "${var.project_name}-ec2-sg"
  description = "Security group for Greeks Collector EC2"
  vpc_id      = data.aws_vpc.default.id

  # SSH access (restrict to your IP in production)
  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]  # Change to your IP
  }

  # Outbound internet access (for API calls)
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.project_name}-ec2-sg"
  }
}

# Security Group for RDS
resource "aws_security_group" "rds_sg" {
  name        = "${var.project_name}-rds-sg"
  description = "Security group for Greeks Collector RDS"
  vpc_id      = data.aws_vpc.default.id

  # PostgreSQL from EC2 only
  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.ec2_sg.id]
  }

  tags = {
    Name = "${var.project_name}-rds-sg"
  }
}

# DB Subnet Group
resource "aws_db_subnet_group" "main" {
  name       = "${var.project_name}-db-subnet"
  subnet_ids = data.aws_subnets.default.ids

  tags = {
    Name = "${var.project_name}-db-subnet"
  }
}

# RDS PostgreSQL Instance (Optional - can use local PostgreSQL to save costs)
resource "aws_db_instance" "greeks_db" {
  identifier           = "${var.project_name}-db"
  allocated_storage    = 20
  storage_type         = "gp2"
  engine               = "postgres"
  engine_version       = "15"
  instance_class       = var.db_instance_type
  db_name              = "greeksdb"
  username             = "greeks_user"
  password             = "ChangeThisSecurePassword123!"  # Change this!
  parameter_group_name = "default.postgres15"
  skip_final_snapshot  = true
  
  vpc_security_group_ids = [aws_security_group.rds_sg.id]
  db_subnet_group_name   = aws_db_subnet_group.main.name
  
  # Cost saving options
  publicly_accessible    = false
  multi_az               = false
  backup_retention_period = 7
  
  tags = {
    Name = "${var.project_name}-db"
  }
}

# IAM Role for EC2
resource "aws_iam_role" "ec2_role" {
  name = "${var.project_name}-ec2-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ec2.amazonaws.com"
        }
      }
    ]
  })
}

# CloudWatch Logs policy
resource "aws_iam_role_policy_attachment" "cloudwatch_logs" {
  role       = aws_iam_role.ec2_role.name
  policy_arn = "arn:aws:iam::aws:policy/CloudWatchAgentServerPolicy"
}

# SSM policy for Session Manager access
resource "aws_iam_role_policy_attachment" "ssm" {
  role       = aws_iam_role.ec2_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

# Instance Profile
resource "aws_iam_instance_profile" "ec2_profile" {
  name = "${var.project_name}-ec2-profile"
  role = aws_iam_role.ec2_role.name
}

# EC2 Instance
resource "aws_instance" "greeks_collector" {
  ami                    = "ami-0522ab6e1ddcc7055"  # Ubuntu 22.04 ap-south-1
  instance_type          = var.instance_type
  vpc_security_group_ids = [aws_security_group.ec2_sg.id]
  iam_instance_profile   = aws_iam_instance_profile.ec2_profile.name
  
  # Enable detailed monitoring for better insights (adds ~$2/month)
  monitoring = true
  
  # Root volume
  root_block_device {
    volume_size = 30
    volume_type = "gp3"
    encrypted   = true
  }
  
  # User data script to install dependencies
  user_data = <<-EOF
    #!/bin/bash
    apt update && apt upgrade -y
    apt install -y python3.11 python3.11-venv python3-pip postgresql-client build-essential libpq-dev
    
    # Create app directory
    mkdir -p /home/ubuntu/angelone_greeks_collector
    chown ubuntu:ubuntu /home/ubuntu/angelone_greeks_collector
  EOF

  tags = {
    Name = "${var.project_name}-ec2"
  }
}

# CloudWatch Alarm for high CPU (free tier includes 10 alarms)
resource "aws_cloudwatch_metric_alarm" "cpu_high" {
  alarm_name          = "${var.project_name}-cpu-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "CPUUtilization"
  namespace           = "AWS/EC2"
  period              = 300
  statistic           = "Average"
  threshold           = 80
  alarm_description   = "CPU utilization is above 80%"
  
  dimensions = {
    InstanceId = aws_instance.greeks_collector.id
  }
}

# Outputs
output "ec2_public_ip" {
  value       = aws_instance.greeks_collector.public_ip
  description = "Public IP of the EC2 instance"
}

output "ec2_instance_id" {
  value       = aws_instance.greeks_collector.id
  description = "EC2 Instance ID"
}

output "rds_endpoint" {
  value       = aws_db_instance.greeks_db.endpoint
  description = "RDS PostgreSQL endpoint"
}

output "monthly_cost_estimate" {
  value = <<-EOT
    
    Estimated Monthly Cost Breakdown:
    ---------------------------------
    EC2 t3.small:     ~$15
    RDS db.t3.micro:  ~$12
    EBS 30GB gp3:     ~$2.50
    Data Transfer:    ~$1-2
    CloudWatch:       ~$1
    ---------------------------------
    Total:            ~$31-33/month
    
    With $100 credit and 184 days:
    - Budget per month: ~$16
    - To stay in budget, use local PostgreSQL instead of RDS
    
    Cost-Saving Alternative (EC2 + Local PostgreSQL):
    EC2 t3.small:     ~$15
    EBS 30GB gp3:     ~$2.50
    Total:            ~$17.50/month
    
  EOT
}
