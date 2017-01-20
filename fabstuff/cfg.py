
#
# Setting configuration parameters
#

from fabric.api import env, task, abort
from collections import namedtuple

Profile = namedtuple("Profile", ["cluster", "lb", "task_def"])

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

@task
def timeout(*args):
    """Sets the container timeout"""
    assert len(args) == 1, "Requires a single argument"
    env.container_timeout = int(args[0])

def build_dir(version): return "build-docker/%s/" % version

def check_attr(env, attr_name, cfg_task_name, readable_name):

    if not hasattr(env, attr_name):
        abort("Must supply %s with task:\n\tfab %s:<%s> <other tasks>" \
            % (readable_name, cfg_task_name, readable_name))

    return getattr(env, attr_name)

# checkers
revision = lambda env: check_attr(env, "revision",    "rev",  "ecs revision")
version  = lambda env: check_attr(env, "app_version", "ver",  "application version")
profile  = lambda env: check_attr(env, "profile",     "prof", "application profile (dev/prod)")
lb       = lambda env: check_attr(env, "lb",          "",     "")
task_def = lambda env: check_attr(env, "task_def",    "",     "")
container_timeout = lambda env: check_attr(env, "container_timeout", "timeout", "application timeout (in seconds)")

def load_profile(profiles): # profile: dict(string, Profile)
    prof_name = profile(env)
    assert prof_name in profiles, "Missing profile " + prof_name
    prof = profiles[prof_name]

    env.CLUSTER = prof.cluster
    env.lb = prof.lb
    env.task_def = prof.task_def

def load_kv_from_file(*filenames):
    merged = []
    for kv in list(map(_load_kv_from_file, filenames)):
        merged += kv
    return merged

def _load_kv_from_file(filename):
    def split_at_first(splitter):
        return lambda st: tuple(map(str.strip, st.split(splitter, 1)))
    return map(split_at_first(" "), filter(bool, open(filename).read().splitlines()))
