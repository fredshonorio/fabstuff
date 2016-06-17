#!/usr/bin/env python2

#
# Building and publishing docker images
#

from fabric.api import task, env
from fabric.contrib.console import confirm
from run import run, cd
from cfg import build_dir

@task
def build(build_args=[], *args):
    """Builds a docker image from the current Dockerfile, tags it with a version. Reqs: version"""
    import cfg

    version =    cfg.version(env)
    profile =    cfg.profile(env)
    dockerfile = "Dockerfile.%s" % profile
    app_v =      "%s:%s" % (env.APP, version)
    b_dir =      build_dir(version)

    build_args_frag = "" if not build_args else \
        " ".join(
            map(lambda t: "--build-arg %s=\"%s\"" % t, build_args)
        )

    with cd(b_dir):
        confirm("Building %s. Continue?" % app_v)

        run("docker build -f %s -t %s %s ." % (dockerfile, app_v, build_args_frag))

        if "notag" in args:
            return

        confirm("Tagging %s in the remote repo. Press any key to continue" % app_v)
        run("docker tag %s %s/%s" % (app_v, env.DOCKER_REPO, app_v))

@task
def push():
    """Pushes all versions to the remote docker repo, or a specific version, if specified. Opts: version"""

    app_v = "%s:%s" % (env.APP, env.app_version) if env.app_version else env.APP
    run("docker push %s/%s" % (env.DOCKER_REPO, app_v))
