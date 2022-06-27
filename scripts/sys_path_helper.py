##############################################################################
# Note: The author has placed this work in the Public Domain, thereby        #
#       relinquishing all copyrights.  Everyone is free to use, modify,      #
# republish, sell or give away this work without prior consent from anybody. #
##############################################################################
#
# This is a helper module which configures sys.path and provides utilities
# which mask some of the differences between MicroPython and CPython.
#
import sys

if sys.version_info < (3, 4, 0):
    raise Exception('Python 3.4+ or MicroPython are required.')

try:
    from os.path import dirname
    path_join = os.path.join
except (ImportError, NameError):
    SEP = '\\' if ('win' in sys.platform) else '/'
    def dirname(fn):
        return fn.rsplit(SEP, 1)[0]
    def path_join(*parts):
        return SEP.join(parts)


def app_root():
    return path_join(dirname(__file__), '..')


sys.path.append(path_join(app_root(), 'submodules', 'upagekite'))
sys.path.append(app_root())
