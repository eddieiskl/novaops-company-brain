#!/usr/bin/env bash
set -euo pipefail

STACK_NAME="novaops-company-brain"
INSTANCE_TYPE="t3.small"
VPC_ID=""
SUBNET_ID=""
ALLOWED_CIDR=""
APPROVE_COSTS="no"

usage() {
  cat <<'EOF'
Usage: deploy/aws/deploy.sh --approve-costs --vpc-id VPC --subnet-id SUBNET \
  --allowed-cidr IP/32 [--instance-type t3.micro|t3.small] [--stack-name NAME]

This creates billable AWS resources. At public us-east-1 list prices, the default
t3.small, one public IPv4 address, 10 GiB gp3 root disk, and small EFS dataset are
about USD 20/month before tax, data transfer, or CPU-credit overage. Delete the
stack when the reviewer no longer needs it.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --approve-costs) APPROVE_COSTS="yes"; shift ;;
    --vpc-id) VPC_ID="${2:-}"; shift 2 ;;
    --subnet-id) SUBNET_ID="${2:-}"; shift 2 ;;
    --allowed-cidr) ALLOWED_CIDR="${2:-}"; shift 2 ;;
    --instance-type) INSTANCE_TYPE="${2:-}"; shift 2 ;;
    --stack-name) STACK_NAME="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ "$APPROVE_COSTS" != "yes" ]]; then
  echo "Refusing to create billable resources without --approve-costs." >&2
  usage >&2
  exit 2
fi

if [[ -z "$VPC_ID" || -z "$SUBNET_ID" || ! "$ALLOWED_CIDR" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}/32$ ]]; then
  echo "Provide an explicit VPC, public subnet, and a single-host --allowed-cidr ending in /32." >&2
  exit 2
fi

if [[ "$INSTANCE_TYPE" != "t3.micro" && "$INSTANCE_TYPE" != "t3.small" ]]; then
  echo "Instance type must be t3.micro or t3.small." >&2
  exit 2
fi

if [[ -n "$(git status --porcelain)" ]]; then
  echo "Refusing to deploy a dirty working tree. Commit and push the exact release first." >&2
  exit 2
fi

RELEASE_SHA="$(git rev-parse HEAD)"
REPOSITORY_URL="$(git remote get-url origin)"
git fetch origin
if ! git merge-base --is-ancestor "$RELEASE_SHA" origin/main; then
  echo "Release $RELEASE_SHA is not present on origin/main." >&2
  exit 2
fi

aws sts get-caller-identity >/dev/null
aws cloudformation deploy \
  --stack-name "$STACK_NAME" \
  --template-file deploy/aws/cloudformation.yaml \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides \
    VpcId="$VPC_ID" \
    PublicSubnetId="$SUBNET_ID" \
    AllowedCidr="$ALLOWED_CIDR" \
    GitCommit="$RELEASE_SHA" \
    RepositoryUrl="$REPOSITORY_URL" \
    InstanceType="$INSTANCE_TYPE" \
  --tags project=novaops-company-brain release-sha="$RELEASE_SHA"

API_URL="$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --query "Stacks[0].Outputs[?OutputKey=='ApiUrl'].OutputValue | [0]" \
  --output text)"

deploy/aws/verify.sh "$API_URL" "$RELEASE_SHA"
printf 'Deployment verified: %s (release %s)\n' "$API_URL" "$RELEASE_SHA"
