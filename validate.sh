#!/bin/bash

export AWS_PAGER=""

set -euo pipefail

echo "------------------------------------------------"
echo "STARTING AUTOMATED VALIDATION"
echo "------------------------------------------------"

INSTANCE_ID="$(terraform output -raw instance_id)"
LAMBDA_NAME="$(terraform output -raw lambda_function_name)"
TOPIC_ARN="$(terraform output -raw sns_topic_arn)"

echo "Using:"
echo "  INSTANCE_ID = $INSTANCE_ID"
echo "  LAMBDA_NAME = $LAMBDA_NAME"
echo "  TOPIC_ARN   = $TOPIC_ARN"

echo -e "\n[1/5] Checking EC2 Instance Status..."
STATE="$(aws ec2 describe-instances \
  --instance-ids "$INSTANCE_ID" \
  --query 'Reservations[0].Instances[0].State.Name' \
  --output text)"

echo "Result: Instance $INSTANCE_ID is $STATE"

if [[ "$STATE" != "running" ]]; then
  echo "Error: Instance $INSTANCE_ID is not running"
  exit 1
fi

echo -e "\n[2/5] Verifying Lambda Configuration..."
aws lambda get-function-configuration \
  --function-name "$LAMBDA_NAME" \
  --query '{Handler:Handler,Runtime:Runtime,State:State}' \
  --output table

ROLE_ARN="$(aws lambda get-function-configuration --function-name "$LAMBDA_NAME" --query 'Role' --output text)"
ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
REGION="$(aws configure get region)"
REGION="${REGION:-us-east-1}"

SIM_DECISION="$(aws iam simulate-principal-policy \
  --policy-source-arn "$ROLE_ARN" \
  --action-names ec2:RebootInstances \
  --resource-arns "arn:aws:ec2:${REGION}:${ACCOUNT_ID}:instance/${INSTANCE_ID}" \
  --query 'EvaluationResults[0].EvalDecision' \
  --output text)"

echo "IAM simulation result: $SIM_DECISION"

echo -e "\n[3/5] Simulating Latency Alert (Invoking Lambda)..."

cat > /tmp/pe-alert.json << EOF
{
  "alertName": "api-data-latency",
  "triggeredAt": "2026-01-27T12:00:00Z",
  "instance_id": "$INSTANCE_ID",
  "details": {
    "endpoint": "/api/data",
    "threshold_ms": 3000,
    "count_in_10m": 6
  }
}
EOF

echo "Payload:"
cat /tmp/pe-alert.json
echo

START_MS="$(python3 - << 'PY'
import time
print(int(time.time() * 1000))
PY
)"

aws lambda invoke \
  --function-name "$LAMBDA_NAME" \
  --payload fileb:///tmp/pe-alert.json \
  /tmp/response.json --no-cli-pager >/dev/null

LAMBDA_RESPONSE="$(cat /tmp/response.json)"
echo "Lambda Response: $LAMBDA_RESPONSE"

if echo "$LAMBDA_RESPONSE" | grep -q '"statusCode": 200'; then
  echo "IAM permission validated via successful Lambda execution"
else
  echo "IAM permission validation failed"
  exit 1
fi

echo -e "\n[4/5] Checking CloudWatch Logs for Reboot Command..."
sleep 8

aws logs filter-log-events \
  --log-group-name "/aws/lambda/$LAMBDA_NAME" \
  --start-time "$START_MS" \
  --limit 50 \
  --query 'events[*].message' \
  --output text

echo -e "\n[5/5] Confirming SNS Topic..."
aws sns get-topic-attributes \
  --topic-arn "$TOPIC_ARN" \
  --query 'Attributes.TopicArn' \
  --output text

echo -e "\n------------------------------------------------"
echo "VALIDATION COMPLETE"
echo "Verify receipt of the SNS notification in your inbox."
echo "------------------------------------------------"
