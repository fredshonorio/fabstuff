
__all__ = ["services", "update"]

#
# Updating and listing ECS task definitions
#

import sys, json
from fabric.api import task, prompt, env, execute
from fabric.contrib.console import confirm
from fabric.colors import green
from pprint import pformat
from time import sleep
from run import run, capture
import cfg
from subprocess import check_output

@task(name="update-task")
def update_task():
    """Copies the most recent task definition (in ECS) to use a given docker image version. Reqs: version"""

    version = cfg.version(env)

    task_defs_cmd = capture("aws ecs list-task-definitions")
    all_defs = json.loads(task_defs_cmd)["taskDefinitionArns"]

    app_defs = filter(lambda d: ("task-definition/%s" % env.APP) in d, all_defs)
    last_def = sorted(app_defs, key=task_def_revision)[-1]
    last_pretty = pretty_def(last_def)
    app_defs_str = "\n".join(app_defs)

    confirm("Definition choices are:\n%(app_defs_str)s\n\nCreating definition based on\n\n\t%(last_pretty)s\n\nusing docker image version %(version)s\nContinue?""" % locals())

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
def update():
    """Updates a docker cluster to a new revision. Reqs: version"""

    execute(update_task)
    capture("aws ecs update-service --cluster %s --service %s --task-definition %s" % (env.CLUSTER, env.SERVICE, env.APP))
    execute(wait_for_revision)


@task
def wait_for_revision():
    """Polls until one or more containers are running a given revision. Reqs: revision"""

    rev = cfg.revision(env)
    pretty = green("%s:%d" % (env.APP, rev), bold=True)
    print "Waiting for containers running revision %s" % pretty
    revision_str = "task-definition/%s:%d" % (env.APP, rev)

    while True:
        deployments = describe_service()["deployments"]

        running_new_primaries = filter(
            lambda x: x["status"] == "PRIMARY" \
                and x["taskDefinition"].endswith(revision_str) \
                and x["runningCount"] > 0,
            deployments)

        r_count = len(running_new_primaries)

        if r_count > 0:
            print "Found %d running primaries with definition %s, resuming." % (r_count, pretty)
            break

        sleep(3)

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
