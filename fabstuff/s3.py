
# This is not used

from run import capture, run
from fabric.colors import green
from fabric.api import task, env

def publish(files, app, version, s3_bucket):

    v = make_semantic_version(version)

    # assert version does not exist and is newer

    old = _list_versions(s3_bucket, app)

    last = old[-1] if old else None

    assert v > last

    for f in files:
        run("aws s3 cp %(f)s s3://%(s3_bucket)s/%(app)s/%(version)s/" % locals())


@task(name="ls-versions")
def list_versions():
    vs = _list_versions(env.S3_BUCKET, env.APP)

    print "Listing versions in %s for %s\n" % (green(env.S3_BUCKET), green(env.APP, bold=True))

    vs_sorted = map(print_semantic_version, sorted(vs))

    for v in vs_sorted:
        print '\t' + v


def _list_versions(repo, app):

    path = "s3://%s/%s/" % (repo, app)
    resp = capture("aws s3 ls %s" % path)

    versions = \
        map(make_semantic_version,
        map(clean,
        filter(lambda x: x.startswith("PRE"),
        map(lambda x: x.strip(),
        resp.split("\n")))))

    return versions

# ?
def clean(s): return str(s.split(" ")[1].split("/")[0])


def print_semantic_version(semver):

    def print_n_part(ns): return ".".join(map(str, ns))

    if isinstance(semver[-1], str):
        return print_n_part(semver[:-1]) + "-" + semver[-1]
    else:
        return print_n_part(semver)

def make_semantic_version(s):

    if "-" in s:
        tag = s[s.find("-") + 1:]
        n_part = s[:s.find("-")]
    else:
        tag = None
        n_part = s

    ns = tuple(map(int, n_part.split(".")))

    assert 2 <= len(ns) <= 3

    return ns + (tag,) if tag else ns
