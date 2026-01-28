variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "instance_type" {
  type    = string
  default = "t2.micro"
}

variable "instance_name" {
  type    = string
  default = "WebApp-Server"
}

variable "sns_topic_name" {
  type    = string
  default = "performance-alerts-topic"
}

variable "lambda_role_name" {
  type    = string
  default = "lambda_remediation_role"
}

variable "lambda_policy_name" {
  type    = string
  default = "lambda_remediation_policy"
}

variable "lambda_function_name" {
  type    = string
  default = "performance-remediation"
}

variable "lambda_source_dir" {
  type    = string
  default = "../lambda_function"
}

variable "vpc_id" {
  type        = string
  description = "The ID of the target VPC"
}

variable "subnet_id" {
  type        = string
  description = "The ID of the target Subnet"
}

variable "notification_email" {
  description = "Email address for SNS alerts"
  type        = string
  default     = "jordandn6@outlook.com"
}