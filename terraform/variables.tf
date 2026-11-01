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
  description = "Email address for SNS remediation and on-call alerts"
  default     = "jordandn6@outlook.com"
}

variable "oncall_topic_name" {
  type        = string
  description = "SNS topic name for the human-escalation / on-call path"
  default     = "remediation-oncall"
}

variable "state_table_name" {
  type        = string
  description = "DynamoDB table holding remediation attempt history for cooldown + circuit breaker"
  default     = "remediation-state"
}

variable "metric_namespace" {
  type        = string
  description = "CloudWatch namespace for remediation custom metrics"
  default     = "Remediation"
}

variable "cooldown_seconds" {
  type        = number
  description = "Debounce window — suppress a repeat action within this many seconds of the last one"
  default     = 900
}

variable "circuit_window_seconds" {
  type        = number
  description = "Rolling window over which repeated attempts are counted toward the circuit breaker"
  default     = 3600
}

variable "max_attempts" {
  type        = number
  description = "Attempts allowed within the circuit window before remediation halts and escalates to on-call"
  default     = 3
}

variable "dry_run" {
  type        = bool
  description = "When true, run the full gate + telemetry path but skip the mutating AWS calls"
  default     = false
}
