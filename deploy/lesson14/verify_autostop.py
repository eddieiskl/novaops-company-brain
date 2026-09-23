"""After smoke checks pass, exercise the existing stop target on the app service."""
import datetime as dt
import json
import time
import cloud_run as cloud

proof=json.loads((cloud.HERE/'evidence/cloud-verification.json').read_text())
assert proof.get('approval_survives_task_replacement') is True
assert all(v is True for v in proof.values() if isinstance(v,bool))
scheduler=cloud.aws('scheduler')
original=scheduler.get_schedule(Name=cloud.state['stack']+'-app-stop')
name=cloud.state['stack']+'-verify-stop'
when=(dt.datetime.now(dt.timezone.utc)+dt.timedelta(seconds=30)).strftime('%Y-%m-%dT%H:%M:%S')
scheduler.create_schedule(Name=name,ScheduleExpression='at('+when+')',ScheduleExpressionTimezone='UTC',FlexibleTimeWindow={'Mode':'OFF'},ActionAfterCompletion='DELETE',Target=original['Target'])
cloud.record('schedules',name)
print('Scheduled verification of the same automatic-stop target.',flush=True)
end=time.monotonic()+210
passed=False
while time.monotonic()<end:
    service=cloud.aws('ecs').describe_services(cluster=cloud.state['cluster'],services=['app'])['services'][0]
    if service['desiredCount']==0:
        passed=True;break
    time.sleep(10)
(cloud.HERE/'evidence/cloud-autostop.json').write_text(json.dumps({'passed':passed,'schedule':name,'desired_count':service['desiredCount'],'same_target_as_one_hour_guard':True},indent=2)+'\n')
assert passed,'Scheduler did not reduce app desiredCount to zero before the deadline'
print('Automatic stop verified: app desiredCount is zero.',flush=True)
