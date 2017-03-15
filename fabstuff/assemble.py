

from fabric.api import env, task
import cfg
from run import run, cd
from os import path
from docker import get_version

@task
def assemble():
    """Creates a build/$version directory with the artifacts to bake into the docker image"""

    v     = get_version(env)
    prof  = cfg.profile(env)
    files = env.PROJECT_FILES
    build = cfg.build_dir(v)

    run("mkdir -p %s" % build)

    for f in files:
        expanded_path = f % env
        recurse = "-r " if path.isdir(expanded_path) else " "

        run("cp %s%s %s" % (recurse, expanded_path, build))
