#!/usr/bin/env python2

#
#

from fabric.api import  env
from fabric.utils import abort
from run import capture
from collections import namedtuple


# -- ex: 0.0.1-e340[-0]
ImageVersion = namedtuple('ImageVersion', ['app_version', 'git_short_hash', 'build_number'])

def try_parse_image_version(st):
    try:
        return parse_image_version(st)
    except Exception as e:
        print st + ": " + str(e)
        return None

def try_int(i):
    try:
        return int(i)
    except:
        return None

def parse_image_version(st):
    tmp = st.rsplit("-", 1)

    if len(tmp) == 2 and try_int(tmp[1]) is not None:
        assert tmp[1] != "", "Empty build number"
        bn = int(tmp[1])
        rest = tmp[0]
    elif len(tmp) == 2:
        bn = 0
        rest = st
    else:
        bn = 0
        rest = tmp[0]

    ver, hash = rest.rsplit("-", 1)
    assert ver and hash, "Empty version or hash"

    return ImageVersion(ver, hash, bn)

def show(image_version):

    if image_version.build_number == 0:
        return "%s-%s" % (image_version.app_version, image_version.git_short_hash)
    else:
        return "%s-%s-%d" % image_version

# ImageVersion -> [string] -> int
def guess_build_number(tentative, images):

    known_versions = filter(bool,
                     map(try_parse_image_version,
                     filter(lambda i: "latest" not in i,
                     images)))

    same_versions = filter(
        lambda v: v.app_version == tentative.app_version
                  and v.git_short_hash == tentative.git_short_hash,
        known_versions
    )

    bns = list(map(lambda v: v.build_number or 0, same_versions))

    return 0 if not bns else max(bns) + 1

def get_HEAD_short_hash():
    # ensure tree is clean
    diff = capture("(git status --porcelain 2>/dev/null) | wc -l")
    assert int(diff) == 0, "Working tree is not clean"

    # get git hash
    hash = capture("git rev-parse --short HEAD").splitlines()[0]

    return hash

def warn_same_app_version(app_ver, images):

    known_versions = filter(bool, map(try_parse_image_version, images))
    same_versions = filter(lambda v: v.app_version == app_ver, known_versions)

    s = list(same_versions)

    if s:
        print "There appear to be images with the same version as yours: "
        for x in s:
            print x

        answer = raw_input("Continue [Y/n]")

        if answer not in ["Y", "y"]:
            abort("Aborted by user")

# str -> [str] -> str
def git_image_version(app_ver, all_images): # string, [string]
    assert app_ver, "You have not provided a version"

    # warns if you're trying to add a v-<hash>-<build>, but an equal v already exists
    warn_same_app_version(app_ver, all_images)

    short_hash = get_HEAD_short_hash()
    tentative = ImageVersion(app_ver, short_hash, 0)

    build_num = guess_build_number(tentative, all_images)

    return show(ImageVersion(app_ver, short_hash, build_num))
