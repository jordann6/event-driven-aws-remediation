variable "aws_region" {
  type        = string
  description = "AWS region"
  default     = "us-east-1"
}

variable "instance_name" {
  type        = string
  description = "Name tag for the EC2 instance"
  default     = "app-server"
}

variable "sns_topic_name" {
  type        = string
  description = "SNS topic name for remediation alerts"
  default     = "remediation-alerts"
}

variable "lambda_role_name" {
  type        = string
  description = "IAM role name for the remediation Lambda"
  default     = "remediation-lambda-role"
}

variable "lambda_policy_name" {
  type        = string
  description = "IAM policy name for the remediation Lambda"
  default     = "remediation-lambda-policy"
}

variable "lambda_function_name" {
  type        = string
  description = "Lambda function name"
  default     = "event-driven-remediation"
}

variable "lambda_source_dir" {
  type        = string
  description = "Path to the Lambda source directory"
  default     = "../lambda_function"
}

variable "vpc_id" {
  type        = string
  description = "VPC ID for the EC2 instance"
}

variable "subnet_id" {
  type        = string
  description = "Subnet ID for the EC2 instance"
}

variable "notification_email" {
  type        = string
  description = "Email address for SNS remediation alerts"
  default     = "jordandn6@outlook.com"
}
