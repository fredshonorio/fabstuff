#!/usr/bin/env python2

#
# Building and publishing docker images
#

import glob
import cfg
from fabric.api import task, env
from fabric.contrib.console import confirm
from run import run, cd
from cfg import build_dir
from subprocess import call

# fuck it, dup with docker.py
def env_repo_name():
    return env.get("REPO_NAME") or env.APP


def flatten(xss): return [x for xs in xss for x in xs]

#
# reads env: version, profile, APP, image_version
#

def get_version(env):
    return env.get("image_version") or cfg.version(env)

@task
def build(build_args=[], *args):
    """Builds a docker image from the current Dockerfile, tags it with a version. Reqs: version"""
    import cfg

    version =    get_version(env)
    profile =    cfg.profile(env)
    app_v =      "%s:%s" % (env_repo_name(), version)
    b_dir =      build_dir(version)

    build_args_frag = [] if not build_args else flatten(map(lambda t: ["--build-arg", "%s=%s" % t], build_args))
    yes = env.get("yes") or False

    with cd(b_dir):
        dockerfiles = list(glob.glob("Dockerfile*"))
        assert len(dockerfiles) == 1, "Expecting one Dockerfile*, got " + str(dockerfiles)
        dockerfile = dockerfiles[0]

        if yes: print("Building %s." % app_v)
        else:   confirm("Building %s. Continue?" % app_v)

        call(["docker", "build", "-f", dockerfile, "-t", app_v, "-t",  "%s:latest" % env_repo_name()] + build_args_frag + ["."])

@task
def push():
    """Pushes all versions to the remote docker repo, or a specific version, if specified. Opts: version"""
    import cfg

    version    = get_version(env)
    app_v      = "%s:%s" % (env_repo_name(), version)
    app_latest = "%s:latest" % (env_repo_name())

    yes = env.get("yes") or False

    if yes: print("Tagging %s in the remote repo." % app_v)
    else:   confirm("Tagging %s in the remote repo. Press any key to continue" % app_v)

    run("docker tag %s %s/%s" % (app_v, env.DOCKER_REPO, app_v))
    run("docker tag %s %s/%s" % (app_v, env.DOCKER_REPO, app_latest))

    run("docker push %s/%s" % (env.DOCKER_REPO, app_v))
    run("docker push %s/%s" % (env.DOCKER_REPO, app_latest))
