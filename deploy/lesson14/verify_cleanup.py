"""Verify only the resources recorded for this isolated cloud exercise."""
import json
import time
from botocore.exceptions import ClientError
import cloud_run as cloud


def missing(call, codes):
    try:
        call()
        return False
    except ClientError as exc:
        if exc.response['Error']['Code'] in codes:return True
        raise


def inspect():
    s=cloud.state;a=cloud.aws;r={}
    if s.get('filesystem'):r['file_system_removed']=missing(lambda:a('efs').describe_file_systems(FileSystemId=s['filesystem']),['FileSystemNotFound'])
    if s.get('access_point'):r['access_point_removed']=missing(lambda:a('efs').describe_access_points(AccessPointId=s['access_point']),['AccessPointNotFound'])
    if s.get('namespace'):r['namespace_removed']=missing(lambda:a('servicediscovery').get_namespace(Id=s['namespace']),['NamespaceNotFound'])
    if s.get('cluster'):
        clusters=a('ecs').describe_clusters(clusters=[s['cluster']])['clusters']
        r['cluster_inactive']=all(c['status']=='INACTIVE' for c in clusters)
    r['security_groups_removed']=not a('ec2').describe_security_groups(Filters=[{'Name':'group-name','Values':[s['stack']+'-*']}])['SecurityGroups']
    for name in s.get('roles',[]):r['role_removed:'+name]=missing(lambda n=name:a('iam').get_role(RoleName=n),['NoSuchEntity'])
    for name in s.get('schedules',[]):r['schedule_removed:'+name]=missing(lambda n=name:a('scheduler').get_schedule(Name=n),['ResourceNotFoundException'])
    for name in s.get('repositories',[]):r['repository_removed:'+name]=missing(lambda n=name:a('ecr').describe_repositories(repositoryNames=[n]),['RepositoryNotFoundException'])
    for arn in s.get('task_definitions',[]):
        r['task_definition_inactive:'+arn.rsplit('/',1)[-1]]=a('ecs').describe_task_definition(taskDefinition=arn)['taskDefinition']['status']=='INACTIVE'
    if s.get('secret'):r['secret_removed']=missing(lambda:a('secretsmanager').describe_secret(SecretId=s['secret']),['ResourceNotFoundException'])
    if s.get('log_group'):r['log_group_removed']=not any(g['logGroupName']==s['log_group'] for g in a('logs').describe_log_groups(logGroupNamePrefix=s['log_group'])['logGroups'])
    return r

if __name__=='__main__':
    deadline=time.monotonic()+180
    while True:
        results=inspect()
        if all(results.values()) or time.monotonic()>deadline:break
        time.sleep(10)
    (cloud.HERE/'evidence/cloud-cleanup.json').write_text(json.dumps({'stack':cloud.state['stack'],'checks':results,'passed':all(results.values())},indent=2)+'\n')
    print(json.dumps(results,indent=2))
    assert all(results.values()),'Resources still present; inspect cleanup evidence'
