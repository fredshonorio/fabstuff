
#
# Run shell commands
#

from fabric.api import abort
from subprocess import check_output, check_call

def run(*args, **kwargs):
    kwargs.update({"shell": True})
    return check_call(*args, **kwargs)

def capture(*args, **kwargs):
    kwargs.update({"shell": True})
    return check_output(*args, **kwargs)

import os

# stolen from: http://stackoverflow.com/a/13197763

class cd:
    """Context manager for changing the current working directory"""
    def __init__(self, newPath):
        self.newPath = os.path.expanduser(newPath)

    def __enter__(self):
        self.savedPath = os.getcwd()
        os.chdir(self.newPath)

    def __exit__(self, etype, value, traceback):
        os.chdir(self.savedPath)
