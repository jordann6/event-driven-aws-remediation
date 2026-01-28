import json
import os
import boto3
from botocore.exceptions import ClientError

ec2 = boto3.client("ec2")
sns = boto3.client("sns")

def lambda_handler(event, context):
    instance_id = None
    if isinstance(event, dict):
        instance_id = event.get("instance_id") or event.get("INSTANCE_ID")

    instance_id = instance_id or os.environ.get("INSTANCE_ID")
    sns_topic_arn = os.environ.get("SNS_TOPIC_ARN")

    if not instance_id or not sns_topic_arn:
        raise ValueError("Missing required values: instance_id (event or env) and SNS_TOPIC_ARN (env)")

    request_id = getattr(context, "aws_request_id", "unknown")

    print(json.dumps({
        "message": "Received latency alert event",
        "request_id": request_id,
        "event": event
    }, default=str))

    try:
        print(json.dumps({
            "message": "Rebooting EC2 instance",
            "request_id": request_id,
            "instance_id": instance_id
        }))

        ec2.reboot_instances(InstanceIds=[instance_id])

        detail = f"Reboot initiated for instance {instance_id}"
        status = "success"

        print(json.dumps({
            "message": detail,
            "request_id": request_id,
            "instance_id": instance_id
        }))

    except ClientError as e:
        status = "failure"
        detail = f"Failed to reboot instance {instance_id}, error {str(e)}"

        print(json.dumps({
            "message": detail,
            "request_id": request_id,
            "instance_id": instance_id
        }))

        raise

    payload = {
        "status": status,
        "action": "ec2:RebootInstances",
        "instance_id": instance_id,
        "request_id": request_id,
        "detail": detail,
        "alert_event_excerpt": event if isinstance(event, dict) else {"raw": str(event)}
    }

    sns.publish(
        TopicArn=sns_topic_arn,
        Subject=f"Automated Remediation {status}, EC2 reboot",
        Message=json.dumps(payload, default=str)
    )

    return {
        "statusCode": 200,
        "body": json.dumps({"status": status, "instance_id": instance_id})
    }
