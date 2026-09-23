# Lesson 14: full RDS-backed course deployment

The separate Exercise 6 course demo ran in AWS account 531575601230, us-east-1, using the dedicated Lesson14 deployer. This complements the final project's separately verified ECS/EFS packaging; it is not that project's production architecture.

## Verified

All nine cloud checks passed: dashboard health; private encrypted RDS; zero retained automated backups; enabled cost guards; a completed live queue/model turn; conversation recall after replacing the worker; unapproved-model refusal; autoscaling bounds of 1–3 workers; and the outstanding-runs-per-task scaling policy. The two completed turns ran on different worker hosts and the replacement recalled the exact conversation marker stored through RDS.

The cloud scaling policy was configured and inspected. Automatic 1→3→1 scaling behavior was previously exercised locally, rather than asserted from these cloud configuration checks. The final Exercise 6 local suite passes 23 tests.

Deployment fixes isolate queue names by stack, schedule service shutdown and database deletion before billable provisioning, encrypt the database, verify each x86 image before push, retain Docker Desktop plugin discovery with temporary registry authentication, and clean up Container Insights logs. The database was reachable only from the task security groups; dashboard access was restricted to the deployer's IP.

## Cleanup and limits

All **32 final cleanup checks passed**, covering RDS and its subnet group, both services through cluster removal, task definitions, queues, schedules, repositories, secret, temporary roles, security groups, application/Container Insights logs, scaling targets, and alarms. The temporary vendor smoke-test queues were also confirmed absent. Standard account service-linked roles remain as nonbillable service prerequisites.

The automatic-stop watcher lost its AWS connection before recording the live transition. On reconnection the database was already absent before manual teardown; the complete service-stop timing test is therefore not claimed. Final teardown was verified independently, including explicit removal of three security groups missed by the shell lookup.

Classroom limitations remain: one small single-AZ database, no retained backups, an IP-restricted HTTP dashboard, and a worker task role shared with its gateway/MCP sidecars. Finished-run status is held in ingress memory, while conversation state and LiteLLM configuration use RDS. This is a temporary exercise deployment, and has been removed.

Local machine evidence is retained under the lesson's `code/local-demo/`: `rds-cloud-verification.json`, `rds-cloud-cleanup.json`, and `rds-cloud-autostop.json`. These contain check results rather than raw conversations and are not uploaded with the project.

On 2026-09-18, the temporary `Lesson14Policy2` inline policy was removed through the signed-in AWS Console. The console confirmed removal and showed only the preserved `Lesson14Deployer` base policy. The sanitized RDS report was published to PR #1 in commit `5dba868378569b9cd02e17ff439172769628b868`.
