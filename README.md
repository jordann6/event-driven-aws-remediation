# PE Coding Test 2026

## Overview

This project implements an automated performance remediation workflow on AWS.  
When a latency threshold is exceeded for a backend API, a Lambda function is triggered to reboot a target EC2 instance and send a notification via SNS.

The goal of this submission is to demonstrate:

- Infrastructure as Code using Terraform
- Event driven remediation using AWS Lambda
- Safe, observable automation with verification and logging
- Practical tradeoffs under time constraints

---

## Architecture Summary

- **EC2**: Target instance to be remediated
- **Lambda**: Performs automated remediation (EC2 reboot)
- **SNS**: Sends notification after remediation
- **CloudWatch Logs**: Captures execution and audit trail
- **Terraform**: Provisions all AWS resources
- **validate.sh**: End to end validation script

---

## Repository Structure

```text
pe-coding-test-2026/
├── lambda_function/
│   └── app.py
├── terraform/
│   ├── main.tf
│   ├── variables.tf
│   ├── outputs.tf
│   └── terraform.tfvars
├── validate.sh
├── sumo_logic_query.txt
└── README.md
```
