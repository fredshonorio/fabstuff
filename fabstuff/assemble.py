

from fabric.api import env, task
import cfg
from run import run, cd

@task
def assemble():
    """Creates a build/$version directory with the artifacts to bake into the docker image"""

    v     = cfg.version(env)
    prof  = cfg.profile(env)
    files = env.PROJECT_FILES
    build = cfg.build_dir(v)

    run("mkdir -p %s" % build)

    for f in files:
        run("cp %s %s" % (f % env, build))
