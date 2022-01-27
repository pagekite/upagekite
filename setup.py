# Publish to pip cheat-sheet:
#
#    1. Commit, Tag
#    2. git push, git push --tags
#    3. rm dist/*
#    4. python3 setup.py sdist
#    5. python3 setup.py bdist_wheel --universal
#    6. twine upload dist/*
#
import setuptools
from distutils.core import setup

from upagekite.proto import UPAGEKITE_VERSION

setup(
  name = 'upagekite',
  packages = ['upagekite'],
  version = UPAGEKITE_VERSION,
  license='GPL-3.0',
  description = "Embeddable/IoT PageKite asyncio web server and framework",
  long_description = """\
NOTE: This ALPHA code - a work in progress! Testing uploads to PyPI.

A minimalistic HTTP server and web "micro-framework" for developing Internet
accessible (not just local/LAN) dynamic web apps. The app is exposed to the
web automatically using the PageKite relay protocol.

uPagekite supports HTTP, streaming file up/downloads and websockets. It is
compatible with asyncio and uasyncio event loops.

See the Tutorial for examples: https://github.com/pagekite/upagekite-tutorial

Developed and tested on CPython 3.x on Linux, and MicroPython on the ESP32.

Licensed under the GPLv3+ by default, proprietary licenses are available
from the author.""",
  author = 'Bjarni R. Einarsson',
  author_email = 'bre@pagekite.net',
  url = 'https://github.com/pagekite/upagekite',
  download_url = 'https://codeload.github.com/pagekite/upagekite/tar.gz/refs/tags/v%su' % UPAGEKITE_VERSION,
  keywords = ['pagekite', 'http', 'websocket', 'esp32', 'micropython'],
  install_requires=[],
  classifiers=[
    'Development Status :: 3 - Alpha',
    'Intended Audience :: Developers',
    'License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)',
    'License :: Other/Proprietary License',
    'Framework :: AsyncIO',
    'Programming Language :: Python :: 3',
    'Programming Language :: Python :: Implementation :: CPython',
    'Programming Language :: Python :: Implementation :: MicroPython',
    'Topic :: Software Development :: Embedded Systems',
    'Topic :: Software Development :: Libraries :: Python Modules',
    'Topic :: Software Development :: Libraries :: Application Frameworks',
    'Topic :: Internet :: WWW/HTTP :: Dynamic Content',
    'Topic :: Internet :: WWW/HTTP :: HTTP Servers'])
