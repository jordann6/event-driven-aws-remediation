"""Guardrail-gate unit tests: cooldown debounce, circuit-breaker escalation,
dry-run, and metric emission. Boto clients are stubbed, no AWS calls made."""
import importlib
import os
import sys
import time
import types
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.update({
    "SNS_TOPIC_ARN": "arn:aws:sns:us-east-1:111122223333:remediation-alerts",
    "ONCALL_TOPIC_ARN": "arn:aws:sns:us-east-1:111122223333:remediation-oncall",
    "INSTANCE_ID": "i-abc123",
    "SG_ID": "sg-abc123",
    "STATE_TABLE": "remediation-state",
    "COOLDOWN_SECONDS": "900",
    "CIRCUIT_WINDOW_SECONDS": "3600",
    "MAX_ATTEMPTS": "3",
    "METRIC_NAMESPACE": "Remediation",
})

import lambda_function.app as app  # noqa: E402


def _reload(dry_run="false"):
    os.environ["DRY_RUN"] = dry_run
    importlib.reload(app)
    app.ec2 = mock.Mock()
    app.sns = mock.Mock()
    app.cw = mock.Mock()
    app.ddb = mock.Mock()
    return app


def _ctx():
    return types.SimpleNamespace(aws_request_id="test-req")


def _ddb_with(attempts):
    """Return a mock ddb whose get_item yields the given epoch attempts."""
    m = mock.Mock()
    m.get_item.return_value = {
        "Item": {"attempts": {"L": [{"N": str(a)} for a in attempts]}}
    } if attempts else {}
    return m


def test_proceed_when_no_history():
    a = _reload()
    a.ddb = _ddb_with([])
    result = a.run_remediation("reboot", "i-abc123", "req", {"source": "aws.cloudwatch"})
    assert result["status"] == "success"
    a.ec2.reboot_instances.assert_called_once()
    # success metric emitted
    assert any(c.kwargs["MetricData"][0]["MetricName"] == "RemediationSuccess"
               for c in a.cw.put_metric_data.call_args_list)


def test_cooldown_debounces_recent_action():
    a = _reload()
    a.ddb = _ddb_with([int(time.time()) - 60])  # acted 1 min ago, inside 15-min cooldown
    result = a.run_remediation("reboot", "i-abc123", "req", {})
    assert result["status"] == "skipped"
    assert result["reason"] == "cooldown"
    a.ec2.reboot_instances.assert_not_called()
    assert any(c.kwargs["MetricData"][0]["MetricName"] == "RemediationSkipped"
               for c in a.cw.put_metric_data.call_args_list)


def test_circuit_opens_and_escalates():
    a = _reload()
    now = int(time.time())
    a.ddb = _ddb_with([now - 300, now - 200, now - 100])  # 3 attempts in window
    result = a.run_remediation("reboot", "i-abc123", "req", {})
    assert result["status"] == "escalated"
    assert result["reason"] == "circuit_open"
    a.ec2.reboot_instances.assert_not_called()
    # paged the on-call topic, not the routine one
    subj = a.sns.publish.call_args.kwargs["Subject"]
    assert "ESCALATION" in subj
    assert any(c.kwargs["MetricData"][0]["MetricName"] == "EscalationTriggered"
               for c in a.cw.put_metric_data.call_args_list)


def test_dry_run_skips_mutation_but_runs_gate():
    a = _reload(dry_run="true")
    a.ddb = _ddb_with([])
    result = a.run_remediation("reboot", "i-abc123", "req", {})
    assert result["status"] == "success"
    assert result["dry_run"] is True
    a.ec2.reboot_instances.assert_not_called()  # mutation skipped
    a.ddb.put_item.assert_called_once()          # but attempt still recorded


def test_expired_attempts_pruned_from_window():
    a = _reload()
    now = int(time.time())
    # two very old attempts (outside 1-hr window) should not count toward the breaker
    a.ddb = _ddb_with([now - 7200, now - 5400])
    result = a.run_remediation("reboot", "i-abc123", "req", {})
    assert result["status"] == "success"


if __name__ == "__main__":
    import sys
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as e:
                failures += 1
                print(f"FAIL {name}: {e}")
    sys.exit(1 if failures else 0)
