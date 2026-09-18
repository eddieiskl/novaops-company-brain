"""Publish locally verified artifacts and update only changed ECS workloads."""
import base64
import json
import os
import subprocess
import tempfile
import cloud_run as cloud

manifest=json.loads((cloud.HERE/'evidence/release-manifest.json').read_text())
verification=json.loads((cloud.HERE/'evidence/local-verification.json').read_text())
assert verification['release']['release_sha']==manifest['source_commit']
assert all(value is True for key,value in verification.items() if key!='release')
registry=f'{cloud.ACCOUNT}.dkr.ecr.{cloud.REGION}.amazonaws.com'
auth=cloud.aws('ecr').get_authorization_token()['authorizationData'][0]
username,password=base64.b64decode(auth['authorizationToken']).decode().split(':',1)
images={};proof={}
with tempfile.TemporaryDirectory(prefix='novaops-ecr-') as temp:
    env={**os.environ,'DOCKER_CONFIG':temp}
    subprocess.run(['docker','login','--username',username,'--password-stdin',registry],input=password,text=True,env=env,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    for name,data in manifest['images'].items():
        repo=cloud.state['stack']+'/'+name
        def lookup():
            return cloud.aws('ecr').batch_get_image(repositoryName=repo,imageIds=[{'imageTag':manifest['source_commit']}]).get('images',[])
        found=lookup()
        if not found:
            tag=registry+'/'+repo+':'+manifest['source_commit']
            subprocess.run(['docker','tag',data['image_id'],tag],check=True,env=env)
            subprocess.run(['docker','push',tag],check=True,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            found=lookup()
        assert found,'Missing registry image'
        image=found[0];definition=json.loads(image['imageManifest'])
        assert definition['config']['digest']==data['image_id'],'Registry/local image mismatch'
        digest=image['imageId']['imageDigest'];images[name]=registry+'/'+repo+'@'+digest
        proof[name]={'registry_digest':digest,'config_matches_tested_image':True}
        print('Verified registry image '+name,flush=True)

aws=cloud.aws('ecs')
fields=['family','taskRoleArn','executionRoleArn','networkMode','containerDefinitions','volumes','placementConstraints','requiresCompatibilities','cpu','memory','runtimePlatform']
for service in ['gateway','app']:
    definition=aws.describe_task_definition(taskDefinition=cloud.state[service+'_task_definition'])['taskDefinition']
    request={key:definition[key] for key in fields if key in definition}
    changed=False
    for container in request['containerDefinitions']:
        name={'api':'agent','mcp':'mcp','gateway':'gateway'}[container['name']]
        if container['image']!=images[name]:container['image']=images[name];changed=True
        if container['name']=='api':
            for variable in container['environment']:
                if variable['name']=='NOVAOPS_RELEASE_SHA' and variable['value']!=manifest['source_commit']:
                    variable['value']=manifest['source_commit'];changed=True
    if changed:
        arn=aws.register_task_definition(**request)['taskDefinition']['taskDefinitionArn']
        cloud.record('task_definitions',arn)
        cloud.save(**{service+'_task_definition':arn})
        aws.update_service(cluster=cloud.state['cluster'],service=service,taskDefinition=arn)
        print('Updated '+service,flush=True)
cloud.save(images=images,release=manifest['source_commit'])
(cloud.HERE/'evidence/cloud-image-verification.json').write_text(json.dumps(proof,indent=2)+'\n')
