
#
# Setting configuration parameters
#

from fabric.api import env, task, abort

@task
def ver(*args):
    """Sets the version"""
    assert len(args) == 1, "Requires a single argument"
    env.app_version = args[0]

@task
def prof(*args):
    """Sets the profile"""
    assert len(args) == 1, "Requires a single argument"
    env.profile = args[0]

@task
def rev(*args):
    """Sets the revision"""
    assert len(args) == 1, "Requires a single argument"
    env.revision = int(args[0])

def build_dir(version): return "build-docker/%s/" % version

def check_attr(env, attr_name, cfg_task_name, readable_name):

    if not hasattr(env, attr_name):
        abort("Must supply %s with task:\n\tfab %s:<%s> <other tasks>" \
            % (readable_name, cfg_task_name, readable_name))

    return getattr(env, attr_name)

revision = lambda env: check_attr(env, "revision",    "rev",  "ecs revision")
version  = lambda env: check_attr(env, "app_version", "ver",  "application version")
profile  = lambda env: check_attr(env, "profile",     "prof", "application profile (dev/prod)")
