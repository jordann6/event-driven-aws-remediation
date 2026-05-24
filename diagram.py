from diagrams import Diagram, Cluster, Edge
from diagrams.aws.compute import EC2, Lambda
from diagrams.aws.management import Cloudwatch, CloudwatchAlarm
from diagrams.aws.integration import SNS, Eventbridge
from diagrams.aws.security import IAMRole

graph_attrs = {
    "fontsize": "13",
    "bgcolor": "white",
    "pad": "0.6",
    "splines": "ortho",
}

node_attrs = {
    "fontsize": "11",
}

with Diagram(
    "Event-Driven AWS Remediation",
    filename="docs/architecture",
    outformat="png",
    show=False,
    direction="LR",
    graph_attr=graph_attrs,
    node_attr=node_attrs,
):
    with Cluster("Target Infrastructure"):
        ec2 = EC2("EC2 Instance\n(app-server)")

    alarm = CloudwatchAlarm("CloudWatch Alarm\nCPU >= 80%\n2 periods × 5 min")
    eb = Eventbridge("EventBridge Rule\nAlarm State → ALARM")

    with Cluster("Remediation Lambda"):
        fn = Lambda("event-driven-remediation\nPython 3.13")
        role = IAMRole("IAM Role\nleast-privilege")

    sns = SNS("SNS Topic\nEmail Alert")
    logs = Cloudwatch("CloudWatch Logs\n14-day retention")

    ec2 >> Edge(label="CPUUtilization metric") >> alarm
    alarm >> Edge(label="state change") >> eb
    eb >> Edge(label="invoke") >> fn
    fn - role
    fn >> Edge(label="reboot / lockdown / tag") >> ec2
    fn >> Edge(label="publish result") >> sns
    fn >> Edge(style="dashed") >> logs
