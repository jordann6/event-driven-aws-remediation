import json
import os
import boto3
from botocore.exceptions import ClientError

ec2 = boto3.client("ec2")
sns = boto3.client("sns")

SNS_TOPIC_ARN = os.environ["SNS_TOPIC_ARN"]
INSTANCE_ID   = os.environ["INSTANCE_ID"]
SG_ID         = os.environ.get("SG_ID", "")

REQUIRED_TAGS = {
    "Environment": "production",
    "ManagedBy":   "terraform",
    "Monitored":   "true",
}


def _notify(subject: str, payload: dict, request_id: str) -> None:
    sns.publish(
        TopicArn=SNS_TOPIC_ARN,
        Subject=subject,
        Message=json.dumps({**payload, "request_id": request_id}, default=str),
    )


def reboot_instance(instance_id: str, request_id: str, trigger_event: dict) -> dict:
    print(json.dumps({"action": "reboot", "instance_id": instance_id, "request_id": request_id}))
    ec2.reboot_instances(InstanceIds=[instance_id])

    payload = {
        "status": "success",
        "action": "ec2:RebootInstances",
        "instance_id": instance_id,
        "trigger": trigger_event,
    }
    _notify(f"[Remediation] EC2 reboot triggered — {instance_id}", payload, request_id)
    return payload


def lockdown_security_group(sg_id: str, request_id: str, trigger_event: dict) -> dict:
    print(json.dumps({"action": "lockdown_sg", "sg_id": sg_id, "request_id": request_id}))

    sg = ec2.describe_security_groups(GroupIds=[sg_id])["SecurityGroups"][0]
    ingress = sg.get("IpPermissions", [])

    revoked = []
    for rule in ingress:
        # Remove any rule that opens a port to the world (0.0.0.0/0 or ::/0)
        open_ipv4 = [r for r in rule.get("IpRanges", []) if r.get("CidrIp") == "0.0.0.0/0"]
        open_ipv6 = [r for r in rule.get("Ipv6Ranges", []) if r.get("CidrIpv6") == "::/0"]
        if open_ipv4 or open_ipv6:
            ec2.revoke_security_group_ingress(
                GroupId=sg_id,
                IpPermissions=[rule],
            )
            revoked.append(rule)

    payload = {
        "status": "success",
        "action": "ec2:RevokeSecurityGroupIngress",
        "sg_id": sg_id,
        "rules_revoked": len(revoked),
        "trigger": trigger_event,
    }
    _notify(f"[Remediation] Security group locked down — {sg_id} ({len(revoked)} rules revoked)", payload, request_id)
    return payload


def enforce_tags(instance_id: str, request_id: str, trigger_event: dict) -> dict:
    print(json.dumps({"action": "enforce_tags", "instance_id": instance_id, "request_id": request_id}))

    reservations = ec2.describe_instances(InstanceIds=[instance_id])["Reservations"]
    existing = {t["Key"]: t["Value"] for t in reservations[0]["Instances"][0].get("Tags", [])}

    missing = {k: v for k, v in REQUIRED_TAGS.items() if k not in existing}
    if missing:
        ec2.create_tags(
            Resources=[instance_id],
            Tags=[{"Key": k, "Value": v} for k, v in missing.items()],
        )

    payload = {
        "status": "success",
        "action": "ec2:CreateTags",
        "instance_id": instance_id,
        "tags_applied": missing,
        "trigger": trigger_event,
    }
    _notify(f"[Remediation] Tags enforced on {instance_id} ({len(missing)} applied)", payload, request_id)
    return payload


def lambda_handler(event, context):
    request_id = getattr(context, "aws_request_id", "local")

    print(json.dumps({"message": "Received event", "request_id": request_id, "event": event}, default=str))

    # EventBridge CloudWatch Alarm state-change events
    if event.get("source") == "aws.cloudwatch":
        return reboot_instance(INSTANCE_ID, request_id, event)

    # Manual / test invocations — route on action field
    action = event.get("action", "reboot")

    if action == "lockdown_sg":
        sg_id = event.get("sg_id") or SG_ID
        if not sg_id:
            raise ValueError("lockdown_sg requires sg_id in event or SG_ID env var")
        return lockdown_security_group(sg_id, request_id, event)

    if action == "enforce_tags":
        instance_id = event.get("instance_id") or INSTANCE_ID
        return enforce_tags(instance_id, request_id, event)

    # Default: reboot
    instance_id = event.get("instance_id") or INSTANCE_ID
    return reboot_instance(instance_id, request_id, event)
