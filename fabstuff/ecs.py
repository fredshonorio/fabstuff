
__all__ = ["services", "update", "images"]

#
# Updating and listing ECS task definitions
#

import sys, json
from fabric.api import task, prompt, env, execute
from fabric.contrib.console import confirm
from fabric.colors import green, yellow
from pprint import pformat
from time import sleep
from run import run, capture
import cfg
from subprocess import check_output

@task(name="update-task")
def update_task_def():
    """Copies the most recent task definition (in ECS) to use a given docker image version. Reqs: version"""

    version = cfg.version(env)

    task_defs_cmd = capture("aws ecs list-task-definitions")
    all_defs = json.loads(task_defs_cmd)["taskDefinitionArns"]

    app_defs = filter(lambda d: ("task-definition/%s" % env.APP) in d, all_defs)
    last_def = sorted(app_defs, key=task_def_revision)[-1]
    last_pretty = pretty_def(last_def)

    confirm("Creating definition based on\n\n\t%(last_pretty)s\n\nusing docker image version %(version)s\nContinue?""" % locals())

    old_def = json.loads(capture("aws ecs describe-task-definition --task-definition %s" % last_def))
    new_def = updated_def_from_old(old_def, image_name_from_version(version, env.DOCKER_REPO))

    confirm("Updated the definition to the following:\n%s\n\nContinue?" % pformat(new_def))
    new_def_json = json.dumps(new_def, separators=(',', ':'))
    created = check_output(["aws", "ecs", "register-task-definition", "--cli-input-json", new_def_json])
    rev = json.loads(created)["taskDefinition"]["revision"]

    env.revision = rev

    print "Success! Created revision %d" % rev

@task
def services():
    """Lists ECS services"""

    s = describe_service()
    del s["events"]
    print json.dumps(s, indent=2)

@task
def images():
    """Lists ECS services"""

    first = True
    nextToken = None
    imgs = []

    while nextToken or first:
        cmd = ["aws", "ecr", "list-images", "--repository-name", env.APP] + \
              ([] if first else ["--next-token", nextToken])
        out = check_output(cmd)
        obj = json.loads(out)
        imgs += obj["imageIds"]
        nextToken = obj.get("nextToken")
        first = False

    images = sorted(filter(bool, map(lambda i: i.get("imageTag"), imgs)))

    for i in images:
        print i

def get_desired_count(svc, cluster):
    svc_out = check_output(["aws", "ecs", "describe-services",
        "--service", svc,
        "--cluster", cluster])
    return int(json.loads(svc_out)["services"][0]["desiredCount"])

@task
def update():
    """Updates a docker cluster to a new revision. Reqs: version"""

    execute(update_task_def)

    desiredCount = max(1, get_desired_count(env.SERVICE, env.CLUSTER))
    check_output(['aws', 'ecs', 'update-service',
        '--cluster', env.CLUSTER,
        '--service', env.SERVICE,
        '--task-definition', env.APP])

    rev = cfg.revision(env)
    uptodate = count_uptodate(env.APP, rev)

    while uptodate < desiredCount:
        expected = uptodate + 1

        task_rev = "%s:%d" % (env.APP, rev)
        task_rev_p = green(task_rev, bold=True)
        print "Expecting %s containers running revision %s" % (yellow(str(expected)), task_rev_p)

        stop_oldest_task(env.APP, env.CLUSTER, env.revision)

        while uptodate < expected:
            uptodate = count_uptodate(env.APP, env.revision)
            sys.stdout.write(".")
            sys.stdout.flush()
            sleep(2)

        sleep(cfg.container_timeout(env))

        lb = "%s-container" % env.APP
        print "Waiting for load balancer %s to be ok"

        while True:
            o = check_output(["aws", "elb", "describe-instance-health", "--load-balancer", lb])
            states = json.loads(o)["InstanceStates"]
            stop = len(list(filter(lambda s: s["State"] == "Inservice", states))) == len(states)
            if stop: break
            sleep(2)

        print
        print "Found one! %s containers running %s" % (green(str(uptodate)), task_rev_p)

def start_new_task(task_rev, cluster):
    check_output(["aws", "ecs", "run-task", "--cluster", cluster, "--task-definition", task_rev])

def get_task_with_taskdef(cluster, task_arn):
    out = check_output(["aws", "ecs", "describe-tasks", "--cluster", cluster, "--tasks", task_arn])
    tasks = json.loads(out)["tasks"]
    assert len(tasks) == 1
    return (task_arn, tasks[0]["taskDefinitionArn"].split("/")[-1])

def rev_n_from_arn(arn):
    return int(arn.split("/")[-1].split(":")[1])

def stop_oldest_task(app, cluster, rev):
    out = check_output(["aws", "ecs", "list-tasks", "--cluster", cluster, "--family", app])
    taskArns = json.loads(out)["taskArns"]
    states = map(lambda task: get_task_with_taskdef(cluster, task), taskArns)
    tasks_not_in_rev = list(filter(lambda t: rev_n_from_arn(t[1]) != rev, states))

    assert tasks_not_in_rev
    task_arn, old_task_rev = sorted(tasks_not_in_rev, key=lambda x: rev_n_from_arn(x[1]))[0]

    print "Stopping task %s with revision %s" % (yellow(task_arn), old_task_rev)
    check_output(["aws", "ecs", "stop-task",
        "--cluster", cluster,
        "--task", task_arn,
        "--reason", "automatic deployment, stopping old task"])

def count_uptodate(app, rev):
    revision_str = "%s:%d" % (app, rev)
    deployments = describe_service()["deployments"]

    running_new_primaries = \
        map(lambda x: x["runningCount"],
        filter(lambda x: x["status"] == "PRIMARY" and x["taskDefinition"].endswith(revision_str),
        deployments))

    return sum(running_new_primaries)

def describe_service():
    r = capture("aws ecs describe-services --cluster %s --service %s" % (env.CLUSTER, env.SERVICE))
    ss = json.loads(r)["services"]
    assert len(ss) == 1
    return ss[0]

def task_def_revision(t_def):
    fragment = "task-definition/%s:" % env.APP
    l = len(fragment)
    idx = t_def.index(fragment)
    return int(t_def[idx + l:])

def image_name_from_version(v, repo):
    return "%s/%s:%s" % (repo, env.APP, v)

def updated_def_from_old(old_def, image):
    """Generates an input json for the "aws ecs register-task-definition",
    copying an older task definition to use a new docker image"""

    root = old_def["taskDefinition"]
    cdefs = root["containerDefinitions"]
    assert len(cdefs) == 1
    cdef = cdefs[0]

    return {
        "family": root["family"],
        "containerDefinitions": [
            {
                "name": cdef["name"],
                "image": image,
                "cpu": cdef["cpu"],
                "memory": cdef["memory"],
                "links": [],
                "portMappings": cdef["portMappings"],
                "essential": cdef["essential"],
                "entryPoint": [], "command": [], "environment": [],
                "mountPoints": [], "volumesFrom": [],
                # elided "hostname", "user", "workingDirectory",
                # "disableNetworking", "privileged", "readonlyRootFilesystem",
                # "dnsServers", "dnsSearchDomains", "extraHosts",
                # "dockerSecurityOptions", "dockerLabels", "ulimits",
                # "logConfiguration"
            }
        ]
        # elided "volumes"
    }

def pretty_def(defn):
    ss = defn.split("/")
    return "/".join(ss[:-1] + [green(ss[-1], bold=True)])
