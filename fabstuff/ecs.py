
__all__ = ["services", "update", "images", "load_task_file"]

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
from docker import get_version
from subprocess import check_output
from collections import namedtuple

ALB = namedtuple('ALB', ["group"])
ELB = namedtuple('ELB', ["name"]) # TODO: deprecate

#
# Reads a json task file with the given filename into a python object.
# Can set the following sections
# - containerDefinitions[0].environment - with the values in the append_to_environment dict
# - family - the the value in the family string
#
def load_task_file(filename, family=None, append_to_environment={}):
    task = json.load(open(filename))
    assert "family" in task, 'This doesn\'t look like a task definition file, missing "family" field'
    new_entries = [{"name": key, "value": value} for key, value in append_to_environment.iteritems()]
    task["containerDefinitions"][0]["environment"] += new_entries
    if family is not None:
        task["family"] = family
    return task

@task
def update_task(task_def):
    version = get_version(env)
    yes = env.get("yes") or False

    image = image_name_from_version(version, env.DOCKER_REPO)
    task_def = mutate_image(task_def, image)

    print("Updated the definition to the following:\n%s\n" % pformat(task_def))
    if not yes: confirm("Continue?")

    task_json = json.dumps(task_def, separators=(',', ':'))
    created = check_output(["aws", "ecs", "register-task-definition", "--cli-input-json", task_json])
    rev = json.loads(created)["taskDefinition"]["revision"]

    env.revision = rev
    print "Success! Created revision %d" % rev

@task(name="update-task") # TODO: deprecate (use only update_task)
def update_task_def(task_def=None):
    """Copies the most recent task definition (in ECS) to use a given docker image version. Reqs: version"""

    if task_def:
        execute(update_task, task_def=task_def)
        return

    version = get_version(env)

    task_defs_cmd = capture("aws ecs list-task-definitions --family-prefix %s --sort DESC" % env.APP)
    all_defs = json.loads(task_defs_cmd)["taskDefinitionArns"]

    app_defs = filter(lambda d: ("task-definition/%s" % env.APP) in d, all_defs)
    last_def = sorted(app_defs, key=task_def_revision)[-1]
    last_pretty = pretty_def(last_def)
    yes = env.get("yes") or False

    print("Creating definition based on\n\n\t%(last_pretty)s\n\nusing docker image version %(version)s" % locals())
    if not yes: confirm("Continue?")

    old_def = json.loads(capture("aws ecs describe-task-definition --task-definition %s" % last_def))
    new_def = updated_def_from_old(old_def, image_name_from_version(version, env.DOCKER_REPO))

    print("Updated the definition to the following:\n%s\n" % pformat(new_def))
    if not yes: confirm("Continue?")

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

def try_int(x):
    try:
        return int(x)
    except:
        return x

def try_semver(st):
    split_label = st.split("-")
    label = list(map(try_int, ([split_label[-1]] if len(split_label) >= 2  else [])))
    ver_without_label = split_label[0]
    return tuple(list(map(try_int, ver_without_label.split("."))) + label)

def get_images():
    """Lists ECS services"""

    first = True
    nextToken = None
    imgs = []

    while nextToken or first:
        cmd = ["aws", "ecr", "list-images", "--repository-name", env_repo_name()] + \
              ([] if first else ["--next-token", nextToken])
        out = check_output(cmd)
        obj = json.loads(out)
        imgs += obj["imageIds"]
        nextToken = obj.get("nextToken")
        first = False

    images = sorted(filter(bool, map(lambda i: i.get("imageTag"), imgs)), key=try_semver)
    return images

@task
def images():
    images = get_images()
    for i in images:
        print i

def get_desired_count(svc, cluster):
    svc_out = check_output(["aws", "ecs", "describe-services",
        "--service", svc,
        "--cluster", cluster])
    return int(json.loads(svc_out)["services"][0]["desiredCount"])

@task
def update(onSuccess=None, task_def=None):
    """Updates a docker cluster to a new revision. Reqs: version"""

    execute(update_task_def, task_def=task_def)
    task_def_family = env.APP if task_def == None else cfg.task_def(env)

    check_output(['aws', 'ecs', 'update-service',
        '--cluster', env.CLUSTER,
        '--service', env.SERVICE,
        '--task-definition', task_def_family])

    rev = cfg.revision(env)

    uptodate = count_uptodate(env.APP, rev)
    desiredCount = get_desired_count(env.SERVICE, env.CLUSTER)

    task_rev = "%s:%d" % (task_def_family, rev)
    task_rev_p = green(task_rev, bold=True)

    print "Expecting %s containers running revision %s" % (yellow(str(desiredCount)), task_rev_p)

    while uptodate < desiredCount:
        uptodate = count_uptodate(task_def_family, env.revision)
        sys.stdout.write(".")
        sys.stdout.flush()
        sleep(2)

    lb = cfg.lb(env)

    print
    print "Waiting for load balancer %s to be ok" % str(lb)

    wait_for_lb(lb, desiredCount)

    print "Found %s containers running %s" % (green(str(uptodate)), task_rev_p)

    if onSuccess:
        onSuccess()

def wait_for_lb(lb, dc):
    if isinstance(lb, ELB):
        wait_for_elb(lb.name, dc)
    elif isinstance(lb, ALB):
        wait_for_alb(lb.group, dc)
    else:
        raise ValueError('Unknown lb type ' + str(lb))

def wait_for_alb(group, desiredCount):
    def assert_single(xs):
        assert len(xs) == 1
        return xs

    # get the groups ARN
    o = check_output(["aws", "elbv2", "describe-target-groups", "--name", group])
    arn = assert_single(json.loads(o)["TargetGroups"])[0]["TargetGroupArn"]

    while True:
        o = check_output(["aws", "elbv2", "describe-target-health", "--target-group-arn", arn])
        states = json.loads(o)["TargetHealthDescriptions"]
        stop = len(list(filter(lambda s: s["TargetHealth"]["State"] == "healthy", states))) >= desiredCount
        if stop: break
        sleep(2)

def wait_for_elb(lbname, desiredCount):
    while True:
        o = check_output(["aws", "elb", "describe-instance-health", "--load-balancer", lbname])
        states = json.loads(o)["InstanceStates"]
        stop = len(list(filter(lambda s: s["State"] == "InService", states))) >= desiredCount
        if stop: break
        sleep(2)

@task
def login():
    run("bash -c '`aws ecr get-login --no-include-email`'")

def rev_n_from_arn(arn):
    return int(arn.split("/")[-1].split(":")[1])

def count_uptodate(task_def_family, rev):
    revision_str = "%s:%d" % (task_def_family, rev)
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
    return _task_def_revision(t_def, env.APP)

def _task_def_revision(t_def, app):
    fragment = "task-definition/%s:" % app
    l = len(fragment)
    idx = t_def.index(fragment)
    return int(t_def[idx + l:])

def env_repo_name():
    return env.get("REPO_NAME") or env.APP

def image_name_from_version(v, repo):
    return "%s/%s:%s" % (repo, env_repo_name(), v)

def mutate_image(task_def, image):
    task_def["containerDefinitions"][0]["image"] = image
    return task_def

def updated_def_from_old(old_def, image):
    """Generates an input json for the "aws ecs register-task-definition",
    copying an older task definition to use a new docker image"""

    root = old_def["taskDefinition"]
    cdefs = root["containerDefinitions"]
    assert len(cdefs) == 1
    cdef = cdefs[0]

    d = {
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

    logConf = cdef.get("logConfiguration")
    if logConf:
        d["containerDefinitions"][0]["logConfiguration"] = logConf

    return d

def pretty_def(defn):
    ss = defn.split("/")
    return "/".join(ss[:-1] + [green(ss[-1], bold=True)])
