"""Isolated ECS/EFS lesson exercise. State is saved after each created resource.
Run with `deploy`, `status`, or `cleanup`. Never prints credentials.
"""
import base64
import datetime as dt
import ipaddress
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import time

import boto3
from botocore.exceptions import ClientError
from dotenv import dotenv_values
import httpx

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
STATE = HERE / '.runtime/cloud-state.json'
REGION = 'us-east-1'
ACCOUNT = '531575601230'
v = dotenv_values(ROOT.parent / 'Lesson-14 - Agent-Serving-Cloud-and-LiteLLM/lesson-14-agent-serving-cloud-and-litellm/.env.deploy')
session = boto3.Session(aws_access_key_id=v['AWS_ACCESS_KEY_ID'], aws_secret_access_key=v['AWS_SECRET_ACCESS_KEY'], aws_session_token=v.get('AWS_SESSION_TOKEN') or None, region_name=REGION)
clients = {}
def aws(name):
    if name not in clients: clients[name] = session.client(name)
    return clients[name]
state = json.loads(STATE.read_text()) if STATE.exists() else {}
def save(**values):
    state.update(values)
    STATE.parent.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(state, indent=2)+'\n'); STATE.chmod(0o600)
def record(kind, value):
    state.setdefault(kind, []).append(value); save()
def wait_for(function, seconds=240):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        result = function()
        if result: return result
        time.sleep(5)
    raise TimeoutError('Timed out waiting for AWS resource')
def policy(statements): return json.dumps({'Version':'2012-10-17','Statement':statements})
def allow(actions, resource, **extra): return {'Effect':'Allow','Action':actions,'Resource':resource,**extra}
def role(suffix, principal, statements):
    name=state['stack']+'-'+suffix
    arn=aws('iam').create_role(RoleName=name,AssumeRolePolicyDocument=policy([{'Effect':'Allow','Principal':{'Service':principal},'Action':'sts:AssumeRole'}]))['Role']['Arn']
    record('roles',name)
    aws('iam').put_role_policy(RoleName=name,PolicyName='lesson',PolicyDocument=policy(statements))
    return arn

def deploy():
    assert not state, 'Existing run state found: inspect status/cleanup before another deploy.'
    identity=aws('sts').get_caller_identity()
    assert identity['Account']==ACCOUNT and identity['Arn'].endswith(':user/Lesson14'), 'Unexpected deployment identity'
    release=json.loads((HERE/'evidence/release-manifest.json').read_text())
    stack='novaops-l14-project-'+secrets.token_hex(3)
    save(stack=stack,release=release['source_commit'],started=dt.datetime.now(dt.timezone.utc).isoformat())
    print('Preparing '+stack,flush=True)
    ec2=aws('ec2');efs=aws('efs');sd=aws('servicediscovery');ecs=aws('ecs')
    vpc=ec2.describe_vpcs(Filters=[{'Name':'is-default','Values':['true']}])['Vpcs'][0]['VpcId']
    subnets=ec2.describe_subnets(Filters=[{'Name':'vpc-id','Values':[vpc]}])['Subnets']
    subnet=next(s for s in subnets if s['MapPublicIpOnLaunch'])['SubnetId']
    caller=str(ipaddress.ip_address(httpx.get('https://checkip.amazonaws.com',timeout=15).text.strip()))+'/32'
    save(subnet=subnet,caller_cidr=caller)
    groups={}
    for name in ['app','gateway','efs']:
        gid=ec2.create_security_group(GroupName=stack+'-'+name,Description='Isolated Lesson 14 '+name,VpcId=vpc)['GroupId']
        record('security_groups',gid);groups[name]=gid
    save(groups=groups)
    for target,port,source in [('app',8080,{'IpRanges':[{'CidrIp':caller}]}),('gateway',4000,{'UserIdGroupPairs':[{'GroupId':groups['app']}]}),('efs',2049,{'UserIdGroupPairs':[{'GroupId':groups['app']}]})]:
        ec2.authorize_security_group_ingress(GroupId=groups[target],IpPermissions=[{'IpProtocol':'tcp','FromPort':port,'ToPort':port,**source}])
    fs=efs.create_file_system(CreationToken=stack,Encrypted=True,PerformanceMode='generalPurpose',ThroughputMode='bursting',Tags=[{'Key':'Name','Value':stack}])['FileSystemId'];save(filesystem=fs)
    wait_for(lambda:efs.describe_file_systems(FileSystemId=fs)['FileSystems'][0]['LifeCycleState']=='available')
    ap=efs.create_access_point(FileSystemId=fs,PosixUser={'Uid':10001,'Gid':10001},RootDirectory={'Path':'/novaops','CreationInfo':{'OwnerUid':10001,'OwnerGid':10001,'Permissions':'0700'}},Tags=[{'Key':'Name','Value':stack}])['AccessPointId'];save(access_point=ap)
    mt=efs.create_mount_target(FileSystemId=fs,SubnetId=subnet,SecurityGroups=[groups['efs']])['MountTargetId'];save(mount_target=mt)
    operation=sd.create_http_namespace(Name=stack,Description='Temporary Lesson 14 gateway discovery',CreatorRequestId=stack)['OperationId'];save(namespace_operation=operation)
    def namespace_ready():
        op=sd.get_operation(OperationId=operation)['Operation']
        if op['Status']=='FAIL':raise RuntimeError('Cloud Map namespace creation failed')
        return op.get('Targets',{}).get('NAMESPACE') if op['Status']=='SUCCESS' else None
    ns=wait_for(namespace_ready);save(namespace=ns)
    nsarn=sd.get_namespace(Id=ns)['Namespace']['Arn'];save(namespace_arn=nsarn)
    logs='/ecs/'+stack;aws('logs').create_log_group(logGroupName=logs);save(log_group=logs)
    aws('logs').put_retention_policy(logGroupName=logs,retentionInDays=1)
    secret=aws('secretsmanager').create_secret(Name=stack+'/runtime',SecretString=json.dumps({'gateway':'sk-'+secrets.token_hex(24),'approval':secrets.token_hex(32)}))['ARN'];save(secret=secret)
    execrole=role('exec','ecs-tasks.amazonaws.com',[
        allow(['ecr:GetAuthorizationToken'],'*'),allow(['ecr:BatchCheckLayerAvailability','ecr:GetDownloadUrlForLayer','ecr:BatchGetImage'],f'arn:aws:ecr:{REGION}:{ACCOUNT}:repository/{stack}/*'),
        allow(['logs:CreateLogStream','logs:PutLogEvents'],f'arn:aws:logs:{REGION}:{ACCOUNT}:log-group:{logs}:*'),allow(['secretsmanager:GetSecretValue'],secret)])
    fsarn=f'arn:aws:elasticfilesystem:{REGION}:{ACCOUNT}:file-system/{fs}'
    aparn=f'arn:aws:elasticfilesystem:{REGION}:{ACCOUNT}:access-point/{ap}'
    approle=role('app','ecs-tasks.amazonaws.com',[allow(['elasticfilesystem:ClientMount','elasticfilesystem:ClientWrite'],fsarn,Condition={'StringEquals':{'elasticfilesystem:AccessPointArn':aparn}}),{'Effect':'Deny','Action':['bedrock:InvokeModel','bedrock:InvokeModelWithResponseStream'],'Resource':'*'}])
    expiry=(dt.datetime.now(dt.timezone.utc)+dt.timedelta(days=1)).strftime('%Y-%m-%dT%H:%M:%SZ')
    gatewayrole=role('gateway','ecs-tasks.amazonaws.com',[allow(['bedrock:InvokeModel','bedrock:InvokeModelWithResponseStream','bedrock:GetInferenceProfile'],[f'arn:aws:bedrock:us-east-1:{ACCOUNT}:inference-profile/us.amazon.nova-2-lite-v1:0','arn:aws:bedrock:*::foundation-model/amazon.nova-2-lite-v1:0'],Condition={'DateLessThan':{'aws:CurrentTime':expiry}})])
    save(execution_role=execrole,app_role=approle,gateway_role=gatewayrole)
    finish_deploy()


def finish_deploy():
    assert state.get('app_role') and not state.get('cluster'), 'Resume is supported only after roles, before cluster creation'
    stack=state['stack'];subnet=state['subnet'];groups=state['groups'];fs=state['filesystem'];ap=state['access_point'];mt=state['mount_target'];nsarn=state['namespace_arn'];logs=state['log_group'];secret=state['secret']
    execrole=state['execution_role'];approle=state['app_role'];gatewayrole=state['gateway_role']
    fsarn=f'arn:aws:elasticfilesystem:{REGION}:{ACCOUNT}:file-system/{fs}'
    aparn=f'arn:aws:elasticfilesystem:{REGION}:{ACCOUNT}:access-point/{ap}'
    release=json.loads((HERE/'evidence/release-manifest.json').read_text())
    efs=aws('efs');ecs=aws('ecs')
    efs.put_file_system_policy(FileSystemId=fs,Policy=policy([allow(['elasticfilesystem:ClientMount','elasticfilesystem:ClientWrite'],fsarn,Principal='*',Condition={'ArnEquals':{'aws:PrincipalArn':approle},'Bool':{'aws:SecureTransport':'true'},'StringEquals':{'elasticfilesystem:AccessPointArn':aparn}}),{'Effect':'Deny','Principal':'*','Action':'elasticfilesystem:Client*','Resource':fsarn,'Condition':{'Bool':{'aws:SecureTransport':'false'}}}]))
    ecs.create_cluster(clusterName=stack);save(cluster=stack)
    stoprole=role('stop','scheduler.amazonaws.com',[allow(['ecs:UpdateService'],[f'arn:aws:ecs:{REGION}:{ACCOUNT}:service/{stack}/{name}' for name in ['app','gateway']])])
    # No task is launched until both independent one-hour cost guards exist.
    stop=(dt.datetime.now(dt.timezone.utc)+dt.timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M:%S')
    time.sleep(15)
    for name in ['app','gateway']:
        schedule=stack+'-'+name+'-stop'
        aws('scheduler').create_schedule(Name=schedule,ScheduleExpression='at('+stop+')',ScheduleExpressionTimezone='UTC',FlexibleTimeWindow={'Mode':'OFF'},ActionAfterCompletion='DELETE',Target={'Arn':'arn:aws:scheduler:::aws-sdk:ecs:updateService','RoleArn':stoprole,'Input':json.dumps({'Cluster':stack,'Service':name,'DesiredCount':0})})
        record('schedules',schedule)
    save(auto_stop_at=stop+'Z')
    print('Storage, roles and automatic stop prepared; pushing tested images.',flush=True)
    finish_images()


def finish_images():
    assert state.get('cluster') and not state.get('task_definitions'), 'Image resume requires cluster and no registered task definitions'
    stack=state['stack'];subnet=state['subnet'];groups=state['groups'];fs=state['filesystem'];ap=state['access_point'];mt=state['mount_target'];nsarn=state['namespace_arn'];logs=state['log_group'];secret=state['secret']
    execrole=state['execution_role'];approle=state['app_role'];gatewayrole=state['gateway_role']
    release=json.loads((HERE/'evidence/release-manifest.json').read_text())
    efs=aws('efs');ecs=aws('ecs')
    registry=f'{ACCOUNT}.dkr.ecr.{REGION}.amazonaws.com';images={}
    auth=aws('ecr').get_authorization_token()['authorizationData'][0]
    username,password=base64.b64decode(auth['authorizationToken']).decode().split(':',1)
    # Isolated Docker auth, never modifies ~/.docker or prints a token.
    with tempfile.TemporaryDirectory(prefix='novaops-ecr-') as temp:
        env={**os.environ,'DOCKER_CONFIG':temp}
        subprocess.run(['docker','login','--username',username,'--password-stdin',registry],input=password,text=True,env=env,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        for name,data in release['images'].items():
            repo=stack+'/'+name
            if repo not in state.get('repositories',[]):
                aws('ecr').create_repository(repositoryName=repo,imageTagMutability='IMMUTABLE');record('repositories',repo)
            image=registry+'/'+repo+':'+release['source_commit']
            def pushed_digest():
                digests=json.loads(subprocess.check_output(['docker','image','inspect','--format','{{json .RepoDigests}}',data['image_id']],text=True,env=env)) or []
                return next((d for d in digests if d.startswith(registry+'/'+repo+'@sha256:')),None)
            digest=pushed_digest()
            if not digest:
                subprocess.run(['docker','tag',data['image_id'],image],check=True,env=env)
                subprocess.run(['docker','push',image],check=True,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                digest=pushed_digest()
            registered=aws('ecr').batch_get_image(repositoryName=repo,imageIds=[{'imageTag':release['source_commit']}])
            if not registered.get('images'):raise RuntimeError('Pushed image is not yet available in ECR')
            image_record=registered['images'][0]
            manifest=json.loads(image_record['imageManifest'])
            if manifest.get('config',{}).get('digest') != data['image_id']:
                raise RuntimeError('Registry image config does not match the tested local image')
            images[name]=registry+'/'+repo+'@'+image_record['imageId']['imageDigest']
            print('Pushed '+name,flush=True)
    save(images=images)
    def container(name,image,environment,secrets_env=None,port=None,command=None):
        item={'name':name,'image':image,'essential':True,'user':'10001:10001','environment':[{'name':k,'value':value} for k,value in environment.items()], 'logConfiguration':{'logDriver':'awslogs','options':{'awslogs-group':logs,'awslogs-region':REGION,'awslogs-stream-prefix':name}}}
        if secrets_env:item['secrets']=[{'name':key,'valueFrom':secret+':'+field+'::'} for key,field in secrets_env.items()]
        if port:item['portMappings']=[{'containerPort':port,'protocol':'tcp','name':name}]
        if command:item['command']=command
        return item
    gateway=container('gateway',images['gateway'],{'AWS_REGION':REGION},{'LITELLM_MASTER_KEY':'gateway'},4000)
    gateway['healthCheck']={'command':['CMD-SHELL',"python -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:4000/health/liveliness',timeout=4)\""],'interval':15,'timeout':5,'retries':6,'startPeriod':60}
    mcp=container('mcp',images['mcp'],{'NOVAOPS_DB_PATH':'/data/novaops.sqlite3','LANGFUSE_TRACING_ENABLED':'false'})
    mcp['mountPoints']=[{'sourceVolume':'state','containerPath':'/data','readOnly':False}]
    mcp['healthCheck']={'command':['CMD-SHELL',"python -c \"from company_brain.mcp_client import MCPToolClient; assert MCPToolClient('http://127.0.0.1:9880/mcp').discover_sync()\""],'interval':15,'timeout':8,'retries':6,'startPeriod':30}
    agent=container('api',images['agent'],{'NOVAOPS_TOOL_MODE':'mcp','NOVAOPS_MCP_URL':'http://127.0.0.1:9880/mcp','NOVAOPS_ANSWER_MODE':'gateway','NOVAOPS_MODEL_BACKEND':'gateway','LITELLM_BASE_URL':'http://gateway:4000','LITELLM_MODEL':'novaops-approved','NOVAOPS_APPROVER_ID':'E018','LANGFUSE_TRACING_ENABLED':'false','NOVAOPS_RELEASE_SHA':release['source_commit']},{'LITELLM_API_KEY':'gateway','NOVAOPS_APPROVAL_TOKEN':'approval'},8080)
    agent['dependsOn']=[{'containerName':'mcp','condition':'HEALTHY'}]
    agent['healthCheck']={'command':['CMD-SHELL',"python -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health/ready',timeout=5)\""],'interval':15,'timeout':8,'retries':6,'startPeriod':45}
    for name,containers,taskrole,cpu,memory in [('gateway',[gateway],gatewayrole,'1024','3072'),('app',[mcp,agent],approle,'1024','2048')]:
        td={'family':stack+'-'+name,'networkMode':'awsvpc','requiresCompatibilities':['FARGATE'],'cpu':cpu,'memory':memory,'runtimePlatform':{'cpuArchitecture':'ARM64','operatingSystemFamily':'LINUX'},'executionRoleArn':execrole,'taskRoleArn':taskrole,'containerDefinitions':containers}
        if name=='app':td['volumes']=[{'name':'state','efsVolumeConfiguration':{'fileSystemId':fs,'transitEncryption':'ENABLED','authorizationConfig':{'accessPointId':ap,'iam':'ENABLED'}}}]
        arn=ecs.register_task_definition(**td)['taskDefinition']['taskDefinitionArn'];record('task_definitions',arn)
        save(**{name+'_task_definition':arn})
    wait_for(lambda:efs.describe_mount_targets(MountTargetId=mt)['MountTargets'][0]['LifeCycleState']=='available')
    for name in ['gateway','app']:
        connect={'enabled':True,'namespace':nsarn}
        if name=='gateway':connect['services']=[{'portName':'gateway','discoveryName':'gateway','clientAliases':[{'port':4000,'dnsName':'gateway'}]}]
        ecs.create_service(cluster=stack,serviceName=name,taskDefinition=state[name+'_task_definition'],desiredCount=1,launchType='FARGATE',platformVersion='LATEST',networkConfiguration={'awsvpcConfiguration':{'subnets':[subnet],'securityGroups':[groups[name]],'assignPublicIp':'ENABLED'}},serviceConnectConfiguration=connect,deploymentConfiguration={'maximumPercent':100,'minimumHealthyPercent':0,'deploymentCircuitBreaker':{'enable':True,'rollback':False}})
        record('services',name)
        if name=='gateway':
            print('Waiting for gateway steady state before starting the application.',flush=True)
            def gateway_ready():
                service=ecs.describe_services(cluster=stack,services=['gateway'])['services'][0]
                if any(d.get('rolloutState')=='FAILED' for d in service['deployments']):raise RuntimeError('Gateway deployment failed')
                return service['runningCount']==1 and all(d.get('rolloutState')=='COMPLETED' for d in service['deployments'])
            wait_for(gateway_ready,600)
    print('Both services launched; use status to watch readiness.',flush=True)

def status():
    if not state.get('cluster'): print(json.dumps({'state':state.get('stack'),'cluster_created':False}));return
    services=aws('ecs').describe_services(cluster=state['cluster'],services=state.get('services',[]))['services'] if state.get('services') else []
    output=[]
    for s in services:
        row={k:s.get(k) for k in ['serviceName','runningCount','pendingCount','desiredCount']};row['events']=[e['message'] for e in s.get('events',[])[:3]];row['deployments']=[{'rolloutState':d.get('rolloutState')} for d in s['deployments']]
        tasks=aws('ecs').list_tasks(cluster=state['cluster'],serviceName=s['serviceName'])['taskArns']
        if tasks:
            details=aws('ecs').describe_tasks(cluster=state['cluster'],tasks=tasks)['tasks'];row['tasks']=[{'arn':t['taskArn'],'status':t['lastStatus'],'health':t.get('healthStatus')} for t in details]
            if s['serviceName']=='app':
                for t in details:
                    for a in t.get('attachments',[]):
                        eni=next((d['value'] for d in a.get('details',[]) if d['name']=='networkInterfaceId'),None)
                        if eni:
                            ip=aws('ec2').describe_network_interfaces(NetworkInterfaceIds=[eni])['NetworkInterfaces'][0].get('Association',{}).get('PublicIp')
                            if ip:save(endpoint='http://'+ip+':8080');row['endpoint']=state['endpoint']
        output.append(row)
    print(json.dumps(output,indent=2))

def cleanup():
    failures=[]
    def attempt(label,fn):
        try:fn();print('Removed '+label,flush=True);return True
        except ClientError as e:
            code=e.response['Error']['Code']
            if code not in ['ResourceNotFoundException','FileSystemNotFound','AccessPointNotFound','MountTargetNotFound','NoSuchEntity','InvalidGroup.NotFound','NamespaceNotFound','ServiceNotFound','RepositoryNotFoundException','ClusterNotFoundException','ServiceNotActiveException']:
                failures.append({'resource':label,'code':code});print('Cleanup pending '+label+': '+code,flush=True);return False
            return True
    ecs=aws('ecs')
    cluster_active = False
    if state.get('cluster'):
        cluster_active = any(c.get('status') == 'ACTIVE' for c in ecs.describe_clusters(clusters=[state['cluster']])['clusters'])
    if cluster_active:
        for name in state.get('services',[]):attempt('service '+name,lambda n=name:ecs.delete_service(cluster=state['cluster'],service=n,force=True))
        candidates=list(set(ecs.list_tasks(cluster=state['cluster'])['taskArns'] + ecs.list_tasks(cluster=state['cluster'],desiredStatus='STOPPED')['taskArns']))
        tasks=[t['taskArn'] for t in ecs.describe_tasks(cluster=state['cluster'],tasks=candidates)['tasks'] if t['lastStatus']!='STOPPED'] if candidates else []
        for task in tasks:attempt('task',lambda t=task:ecs.stop_task(cluster=state['cluster'],task=t,reason='Lesson verification cleanup'))
        if tasks:wait_for(lambda:all(t['lastStatus']=='STOPPED' for t in ecs.describe_tasks(cluster=state['cluster'],tasks=tasks)['tasks']),300)
    for name in state.get('schedules',[]):attempt('schedule '+name,lambda n=name:aws('scheduler').delete_schedule(Name=n))
    if state.get('mount_target'):
        mount_deleted=attempt('mount target',lambda:aws('efs').delete_mount_target(MountTargetId=state['mount_target']))
        def mount_gone():
            try:return not aws('efs').describe_mount_targets(FileSystemId=state['filesystem'])['MountTargets']
            except ClientError as e:return e.response['Error']['Code']=='FileSystemNotFound'
        if mount_deleted:wait_for(mount_gone,300)
    if state.get('access_point'):attempt('access point',lambda:aws('efs').delete_access_point(AccessPointId=state['access_point']))
    if state.get('filesystem'):attempt('file system',lambda:aws('efs').delete_file_system(FileSystemId=state['filesystem']))
    if state.get('namespace'):
        try:
            services=aws('servicediscovery').list_services(Filters=[{'Name':'NAMESPACE_ID','Values':[state['namespace']],'Condition':'EQ'}])['Services']
        except ClientError as exc:
            if exc.response['Error']['Code'] != 'NamespaceNotFound': raise
            services=[]
        for service in services:attempt('discovery service',lambda sid=service['Id']:aws('servicediscovery').delete_service(Id=sid))
        attempt('namespace',lambda:aws('servicediscovery').delete_namespace(Id=state['namespace']))
    if state.get('cluster'):attempt('cluster',lambda:ecs.delete_cluster(cluster=state['cluster']))
    for arn in state.get('task_definitions',[]):attempt('task definition',lambda a=arn:ecs.deregister_task_definition(taskDefinition=a))
    for repo in state.get('repositories',[]):attempt('repository '+repo,lambda r=repo:aws('ecr').delete_repository(repositoryName=r,force=True))
    if state.get('secret'):attempt('runtime secret',lambda:aws('secretsmanager').delete_secret(SecretId=state['secret'],ForceDeleteWithoutRecovery=True))
    for name in reversed(state.get('roles',[])):
        attempt('role policy '+name,lambda n=name:aws('iam').delete_role_policy(RoleName=n,PolicyName='lesson'))
        attempt('role '+name,lambda n=name:aws('iam').delete_role(RoleName=n))
    if state.get('log_group'):attempt('log group',lambda:aws('logs').delete_log_group(logGroupName=state['log_group']))
    for gid in reversed(state.get('security_groups',[])):attempt('security group '+gid,lambda g=gid:aws('ec2').delete_security_group(GroupId=g))
    save(cleanup_failures=failures,cleanup_attempted=dt.datetime.now(dt.timezone.utc).isoformat())
    if failures:raise RuntimeError('Cleanup has pending resources; inspect saved state and retry cleanup')

if __name__=='__main__':
    {'deploy':deploy,'resume-after-roles':finish_deploy,'resume-images':finish_images,'status':status,'cleanup':cleanup}[sys.argv[1]]()
