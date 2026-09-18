"""Live cloud checks; synthetic fixtures only, secret values never enter evidence."""
import contextlib
import hashlib
import io
import json
import time
from pathlib import Path

import httpx
import cloud_run as cloud

results={}
def check(name,condition):
    results[name]=bool(condition)
    print(name+(': passed' if condition else ': FAILED'),flush=True)
    assert condition,name

def endpoint():
    with contextlib.redirect_stdout(io.StringIO()):cloud.status()
    return cloud.state.get('endpoint')

def ready(seconds=480):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        services=cloud.aws('ecs').describe_services(cluster=cloud.state['cluster'],services=['app','gateway'])['services']
        stable=len(services)==2 and all(s['runningCount']==1 and s['pendingCount']==0 and all(d.get('rolloutState')=='COMPLETED' for d in s['deployments']) for s in services)
        if not stable:
            time.sleep(10)
            continue
        url=endpoint()
        try:
            if url and httpx.get(url+'/health/ready',timeout=12).status_code==200:return url
        except httpx.HTTPError:pass
        time.sleep(10)
    raise TimeoutError('Cloud API did not become ready')

def main():
    url=ready()
    print('Cloud API ready.',flush=True)
    client=httpx.Client(base_url=url,timeout=120)
    check('release_matches_tested_source',client.get('/health/version').json()['release_sha']==cloud.state['release'])
    check('liveness',client.get('/health/live').status_code==200)
    base={'thread_id':'cloud-verification','caller':{'employee_id':'E004','user_group':'UG_HR'}}
    check('invalid_input_422',client.post('/v1/agent/turn',json={**base,'message':' '}).status_code==422)
    r=client.post('/v1/agent/turn',json={**base,'message':'May I use my own laptop for work?'})
    check('live_gateway_policy_answer',r.status_code==200 and r.json()['status']=='completed' and bool(r.json()['citations']))
    r=client.post('/v1/agent/turn',json={**base,'message':'Please file the Webex access request for Maya.'})
    check('pending_handoff_202',r.status_code==202 and r.json()['status']=='pending')
    digest=hashlib.sha256(b'maya:E001:webex:S2-onboarding-maya').hexdigest()[:12].upper()
    body={'handoff_id':'HO-'+digest,'approval_id':'AP-H-'+digest,'decision':'approved','reason':'Approved for the synthetic onboarding exercise'}
    check('approval_requires_auth',client.post('/v1/approvals/resume',json=body).status_code==401)
    ecs=cloud.aws('ecs');cluster=cloud.state['cluster']
    old=ecs.list_tasks(cluster=cluster,serviceName='app')['taskArns']
    check('one_application_task',len(old)==1)
    # maxPercent=100/minHealthy=0 prevents concurrent MCP writers during replacement.
    ecs.update_service(cluster=cluster,service='app',forceNewDeployment=True)
    end=time.monotonic()+480
    while time.monotonic()<end:
        active=ecs.list_tasks(cluster=cluster,serviceName='app')['taskArns']
        if active and not set(active)&set(old):break
        time.sleep(10)
    else:raise TimeoutError('Application task was not replaced')
    url=ready();client=httpx.Client(base_url=url,timeout=120)
    secret=json.loads(cloud.aws('secretsmanager').get_secret_value(SecretId=cloud.state['secret'])['SecretString'])
    headers={'Authorization':'Bearer '+secret['approval']}
    first=client.post('/v1/approvals/resume',json=body,headers=headers)
    second=client.post('/v1/approvals/resume',json=body,headers=headers)
    check('approval_survives_task_replacement',first.status_code==200 and first.json()['status']=='blocked')
    check('approval_replay_same_request',second.status_code==200 and first.json()['access_request']['request_id']==second.json()['access_request']['request_id'])
    check('contradictory_decision_409',client.post('/v1/approvals/resume',json={**body,'decision':'rejected'},headers=headers).status_code==409)
    app=ecs.describe_task_definition(taskDefinition=cloud.state['app_task_definition'])['taskDefinition']
    gateway=ecs.describe_task_definition(taskDefinition=cloud.state['gateway_task_definition'])['taskDefinition']
    check('distinct_task_roles',app['taskRoleArn']!=gateway['taskRoleArn'])
    api=next(c for c in app['containerDefinitions'] if c['name']=='api')
    check('api_has_no_provider_keys',not any(e['name'] in ['AWS_ACCESS_KEY_ID','AWS_SECRET_ACCESS_KEY','AWS_SESSION_TOKEN'] for e in api['environment']+api.get('secrets',[])))
    check('api_has_no_data_mount',not api.get('mountPoints'))
    volume=app['volumes'][0]['efsVolumeConfiguration']
    check('efs_tls_iam',volume['transitEncryption']=='ENABLED' and volume['authorizationConfig']['iam']=='ENABLED')
    check('immutable_digest_images',all('@sha256:' in c['image'] for c in app['containerDefinitions']+gateway['containerDefinitions']))
    check('nonroot_workload_containers',all(c['user']=='10001:10001' for c in app['containerDefinitions']+gateway['containerDefinitions']))
    results['stack']=cluster
    results['source_commit']=cloud.state['release']
    results['original_app_task']=old[0]
    results['replacement_app_task']=active[0]

if __name__=='__main__':
    try:main()
    finally:(Path(__file__).parent/'evidence/cloud-verification.json').write_text(json.dumps(results,indent=2)+'\n')
