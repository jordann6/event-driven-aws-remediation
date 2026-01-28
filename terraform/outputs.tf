output "instance_id" {
  value = aws_instance.web_app.id
}

output "sns_topic_arn" {
  value = aws_sns_topic.alerts.arn
}

output "lambda_function_name" {
  value = aws_lambda_function.remediation.function_name
}
