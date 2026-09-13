#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 || "$1" != "--confirm-delete" ]]; then
  echo "Usage: deploy/aws/destroy.sh --confirm-delete [STACK_NAME]" >&2
  exit 2
fi

STACK_NAME="${2:-novaops-company-brain}"
aws cloudformation delete-stack --stack-name "$STACK_NAME"
aws cloudformation wait stack-delete-complete --stack-name "$STACK_NAME"
printf 'Deleted stack %s and its EC2, EFS, network, and IAM resources.\n' "$STACK_NAME"
