#!/usr/bin/env python2

#
#

from fabric.api import task, env
from fabric.contrib.console import confirm
from run import capture
from cfg import build_dir

@task
def prompt_version():
    v = env.get("app_version")
    if v: return v
    v = get_version()
    given_v = raw_input(
        "Detected version: %s\n" % v +
        "What is the version that I should push? (press Enter for %s): " % v)
    env.app_version = given_v or v

def get_version():
    return capture("./gradlew printVersion | grep ':printVersion' -A 1 | tail -n1").split(" ")[0]
