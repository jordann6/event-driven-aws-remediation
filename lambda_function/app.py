import json
import os
import time
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

ec2 = boto3.client("ec2")
sns = boto3.client("sns")
cw = boto3.client("cloudwatch")
ddb = boto3.client("dynamodb")

SNS_TOPIC_ARN = os.environ["SNS_TOPIC_ARN"]
INSTANCE_ID = os.environ["INSTANCE_ID"]
SG_ID = os.environ.get("SG_ID", "")

# --- Guardrail configuration ----------------------------------------------
STATE_TABLE = os.environ.get("STATE_TABLE", "")
ONCALL_TOPIC_ARN = os.environ.get("ONCALL_TOPIC_ARN", SNS_TOPIC_ARN)
COOLDOWN_SECONDS = int(os.environ.get("COOLDOWN_SECONDS", "900"))          # 15 min debounce
CIRCUIT_WINDOW_SECONDS = int(os.environ.get("CIRCUIT_WINDOW_SECONDS", "3600"))  # 1 hr
MAX_ATTEMPTS = int(os.environ.get("MAX_ATTEMPTS", "3"))                     # trip after N in window
DRY_RUN = os.environ.get("DRY_RUN", "false").lower() == "true"
METRIC_NAMESPACE = os.environ.get("METRIC_NAMESPACE", "Remediation")

REQUIRED_TAGS = {
    "Environment": "production",
    "ManagedBy": "terraform",
    "Monitored": "true",
}


# --- Observability ---------------------------------------------------------

def _emit_metric(name: str, action: str, resource_id: str, value: float = 1.0, unit: str = "Count") -> None:
    """Emit a CloudWatch custom metric. Never let telemetry failures break remediation."""
    try:
        cw.put_metric_data(
            Namespace=METRIC_NAMESPACE,
            MetricData=[{
                "MetricName": name,
                "Value": value,
                "Unit": unit,
                "Dimensions": [
                    {"Name": "Action", "Value": action},
                    {"Name": "ResourceId", "Value": resource_id},
                ],
            }],
        )
    except ClientError as e:
        print(json.dumps({"level": "warn", "message": "metric emit failed", "error": str(e)}))


def _notify(topic_arn: str, subject: str, payload: dict, request_id: str) -> None:
    sns.publish(
        TopicArn=topic_arn,
        Subject=subject[:100],  # SNS subject hard limit
        Message=json.dumps({**payload, "request_id": request_id}, default=str),
    )


def _event_latency_ms(trigger_event: dict) -> float | None:
    """Time from alarm firing to remediation, our time-to-remediate signal."""
    ts = trigger_event.get("time")
    if not ts:
        return None
    try:
        fired = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - fired).total_seconds() * 1000.0
    except (ValueError, AttributeError):
        return None


# --- Guardrail gate (cooldown + circuit breaker) ---------------------------

class GateDecision:
    PROCEED = "proceed"
    COOLDOWN = "cooldown"       # too soon since last action, debounce
    CIRCUIT_OPEN = "circuit_open"  # too many attempts in window, escalate to human


def _load_attempts(key: str) -> list[int]:
    """Recent remediation timestamps (epoch seconds) for this resource+action."""
    if not STATE_TABLE:
        return []
    try:
        item = ddb.get_item(
            TableName=STATE_TABLE,
            Key={"resource_action": {"S": key}},
            ConsistentRead=True,
        ).get("Item")
    except ClientError as e:
        print(json.dumps({"level": "warn", "message": "state read failed", "error": str(e)}))
        return []
    if not item or "attempts" not in item:
        return []
    return [int(a["N"]) for a in item["attempts"].get("L", [])]


def _save_attempts(key: str, attempts: list[int]) -> None:
    if not STATE_TABLE:
        return
    ttl = int(time.time()) + CIRCUIT_WINDOW_SECONDS * 2
    try:
        ddb.put_item(
            TableName=STATE_TABLE,
            Item={
                "resource_action": {"S": key},
                "attempts": {"L": [{"N": str(a)} for a in attempts]},
                "expires_at": {"N": str(ttl)},
            },
        )
    except ClientError as e:
        print(json.dumps({"level": "warn", "message": "state write failed", "error": str(e)}))


def evaluate_gate(resource_id: str, action: str) -> tuple[str, list[int]]:
    """Decide whether remediation may proceed. Returns (decision, pruned_attempts)."""
    key = f"{resource_id}#{action}"
    now = int(time.time())
    attempts = [t for t in _load_attempts(key) if now - t < CIRCUIT_WINDOW_SECONDS]

    if len(attempts) >= MAX_ATTEMPTS:
        return GateDecision.CIRCUIT_OPEN, attempts
    if attempts and (now - max(attempts)) < COOLDOWN_SECONDS:
        return GateDecision.COOLDOWN, attempts
    return GateDecision.PROCEED, attempts


def record_attempt(resource_id: str, action: str, attempts: list[int]) -> None:
    key = f"{resource_id}#{action}"
    _save_attempts(key, attempts + [int(time.time())])


def escalate(resource_id: str, action: str, attempts: list[int], request_id: str, trigger_event: dict) -> dict:
    """Circuit is open, prior remediations did not hold. Page a human instead of acting again."""
    payload = {
        "status": "escalated",
        "reason": "circuit_open",
        "action": action,
        "resource_id": resource_id,
        "attempts_in_window": len(attempts),
        "window_seconds": CIRCUIT_WINDOW_SECONDS,
        "detail": f"{action} fired {len(attempts)}x in {CIRCUIT_WINDOW_SECONDS // 60} min without resolving; automated remediation halted, manual intervention required.",
        "trigger": trigger_event,
    }
    _emit_metric("EscalationTriggered", action, resource_id)
    _notify(ONCALL_TOPIC_ARN, f"[ESCALATION] {action} on {resource_id} not resolving — page on-call", payload, request_id)
    print(json.dumps({"level": "error", **payload, "request_id": request_id}))
    return payload


# --- Remediation actions ---------------------------------------------------

def reboot_instance(instance_id: str, request_id: str, trigger_event: dict) -> dict:
    if not DRY_RUN:
        ec2.reboot_instances(InstanceIds=[instance_id])
    payload = {
        "status": "success",
        "action": "ec2:RebootInstances",
        "instance_id": instance_id,
        "dry_run": DRY_RUN,
        "trigger": trigger_event,
    }
    _notify(SNS_TOPIC_ARN, f"[Remediation] EC2 reboot triggered — {instance_id}", payload, request_id)
    return payload


def lockdown_security_group(sg_id: str, request_id: str, trigger_event: dict) -> dict:
    sg = ec2.describe_security_groups(GroupIds=[sg_id])["SecurityGroups"][0]
    ingress = sg.get("IpPermissions", [])

    revoked = []
    for rule in ingress:
        open_ipv4 = [r for r in rule.get("IpRanges", []) if r.get("CidrIp") == "0.0.0.0/0"]
        open_ipv6 = [r for r in rule.get("Ipv6Ranges", []) if r.get("CidrIpv6") == "::/0"]
        if open_ipv4 or open_ipv6:
            if not DRY_RUN:
                ec2.revoke_security_group_ingress(GroupId=sg_id, IpPermissions=[rule])
            revoked.append(rule)

    payload = {
        "status": "success",
        "action": "ec2:RevokeSecurityGroupIngress",
        "sg_id": sg_id,
        "rules_revoked": len(revoked),
        "dry_run": DRY_RUN,
        "trigger": trigger_event,
    }
    _notify(SNS_TOPIC_ARN, f"[Remediation] Security group locked down — {sg_id} ({len(revoked)} rules)", payload, request_id)
    return payload


def enforce_tags(instance_id: str, request_id: str, trigger_event: dict) -> dict:
    reservations = ec2.describe_instances(InstanceIds=[instance_id])["Reservations"]
    existing = {t["Key"]: t["Value"] for t in reservations[0]["Instances"][0].get("Tags", [])}

    missing = {k: v for k, v in REQUIRED_TAGS.items() if k not in existing}
    if missing and not DRY_RUN:
        ec2.create_tags(
            Resources=[instance_id],
            Tags=[{"Key": k, "Value": v} for k, v in missing.items()],
        )

    payload = {
        "status": "success",
        "action": "ec2:CreateTags",
        "instance_id": instance_id,
        "tags_applied": missing,
        "dry_run": DRY_RUN,
        "trigger": trigger_event,
    }
    _notify(SNS_TOPIC_ARN, f"[Remediation] Tags enforced on {instance_id} ({len(missing)} applied)", payload, request_id)
    return payload


ACTIONS = {
    "reboot": (reboot_instance, lambda ev: ev.get("instance_id") or INSTANCE_ID),
    "lockdown_sg": (lockdown_security_group, lambda ev: ev.get("sg_id") or SG_ID),
    "enforce_tags": (enforce_tags, lambda ev: ev.get("instance_id") or INSTANCE_ID),
}


# --- Orchestration ---------------------------------------------------------

def run_remediation(action: str, resource_id: str, request_id: str, trigger_event: dict) -> dict:
    """Gate every remediation through cooldown + circuit breaker, then act, verify, meter."""
    handler, _ = ACTIONS[action]

    decision, attempts = evaluate_gate(resource_id, action)

    if decision == GateDecision.CIRCUIT_OPEN:
        return escalate(resource_id, action, attempts, request_id, trigger_event)

    if decision == GateDecision.COOLDOWN:
        payload = {
            "status": "skipped",
            "reason": "cooldown",
            "action": action,
            "resource_id": resource_id,
            "cooldown_seconds": COOLDOWN_SECONDS,
            "detail": f"{action} ran within the last {COOLDOWN_SECONDS // 60} min; debounced to let the prior action settle.",
        }
        _emit_metric("RemediationSkipped", action, resource_id)
        print(json.dumps({"level": "info", **payload, "request_id": request_id}))
        return payload

    # PROCEED — record the attempt first so a concurrent re-fire sees it
    record_attempt(resource_id, action, attempts)
    print(json.dumps({"level": "info", "message": "remediating", "action": action,
                      "resource_id": resource_id, "dry_run": DRY_RUN, "request_id": request_id}))
    try:
        result = handler(resource_id, request_id, trigger_event)
    except ClientError as e:
        _emit_metric("RemediationFailure", action, resource_id)
        payload = {"status": "failure", "action": action, "resource_id": resource_id, "error": str(e)}
        _notify(ONCALL_TOPIC_ARN, f"[Remediation FAILED] {action} on {resource_id}", payload, request_id)
        print(json.dumps({"level": "error", **payload, "request_id": request_id}))
        raise

    _emit_metric("RemediationSuccess", action, resource_id)
    latency = _event_latency_ms(trigger_event)
    if latency is not None:
        _emit_metric("TimeToRemediateMs", action, resource_id, value=latency, unit="Milliseconds")
    return result


def lambda_handler(event, context):
    request_id = getattr(context, "aws_request_id", "local")
    print(json.dumps({"message": "Received event", "request_id": request_id, "event": event}, default=str))

    # EventBridge CloudWatch Alarm state-change events → auto-reboot path
    if event.get("source") == "aws.cloudwatch":
        return run_remediation("reboot", INSTANCE_ID, request_id, event)

    # Manual / test invocations — route on action field
    action = event.get("action", "reboot")
    if action not in ACTIONS:
        raise ValueError(f"unknown action '{action}'; expected one of {list(ACTIONS)}")

    _, resource_of = ACTIONS[action]
    resource_id = resource_of(event)
    if not resource_id:
        raise ValueError(f"action '{action}' requires a target resource id")

    return run_remediation(action, resource_id, request_id, event)
