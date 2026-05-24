from diagrams import Diagram, Cluster, Edge
from diagrams.aws.compute import EC2, Lambda
from diagrams.aws.management import Cloudwatch, CloudwatchAlarm
from diagrams.aws.integration import SNS, Eventbridge
from diagrams.aws.security import IAMRole

graph_attrs = {
    "fontsize": "13",
    "bgcolor": "white",
    "pad": "0.6",
    "ranksep": "1.0",
    "nodesep": "0.5",
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
    with Cluster("Trigger Chain"):
        ec2_mon = EC2("EC2\napp-server")
        alarm   = CloudwatchAlarm("CloudWatch Alarm\nCPU >= 80% · 2×5 min")
        eb      = Eventbridge("EventBridge\nstate → ALARM")

    with Cluster("Remediation Lambda · Python 3.13"):
        role = IAMRole("IAM Role\nleast-privilege")
        fn   = Lambda("event-driven\nremediation")

    with Cluster("Actions"):
        ec2_fix = EC2("EC2\nreboot / tag")
        sns     = SNS("SNS\nEmail Alert")
        logs    = Cloudwatch("CloudWatch Logs\n14-day retention")

    ec2_mon >> Edge(label="CPUUtilization") >> alarm
    alarm   >> Edge(label="state change")   >> eb
    eb      >> Edge(label="invoke")         >> fn
    role    - fn
    fn      >> ec2_fix
    fn      >> sns
    fn      >> Edge(style="dashed")         >> logs
