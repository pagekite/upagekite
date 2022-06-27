#!/usr/bin/python3
##############################################################################
# Note: The author has placed this work in the Public Domain, thereby        #
#       relinquishing all copyrights.  Everyone is free to use, modify,      #
# republish, sell or give away this work without prior consent from anybody. #
##############################################################################
#
# This is a minimal, single-file uPageKite "hello world" web server.
#
# It should provide responses on the following URL paths:
#
#    /
#    /hello/dynamic
#    /robots.txt
#
import sys
from sys_path_helper import path_join, app_root

import upagekite.proto
from upagekite import uPageKite, LocalHTTPKite
from upagekite.httpd import HTTPD, url
from upagekite.proto import uPageKiteDefaults
from upagekite.web import http_require


# This is a hack so our demo webapp can find its files even if it is
# running locally and not on an actual ESP32.
upagekite.proto.APP_ROOT_PREFIXES = [path_join(app_root(), 'webapp')]

WEB_ROOT = path_join(app_root(), 'webapp', 'webroot')  # Contains index.html & robots.txt
USERS = {}


# This class configures uPageKite for your app; by default it uses the
# pagekite.net public relays and logs very little.
class myPageKiteSettings(uPageKiteDefaults):
    info = uPageKiteDefaults.log
    debug = uPageKiteDefaults.log


def check_userpass(method, data):
    if method != 'basic':
        return False
    username, password = data
    return (USERS.get(username, False) == password)


# Register a simple handler for our dynamic hello page
@url('/hello/dynamic')
@http_require(auth='basic', auth_check=check_userpass)
def web_hello_dynamic(req_env):
    remote_ip = req_env.remote_ip
    user_agent = req_env.http_headers.get('User-Agent', 'Unknown Browser')

    something = req_env['something']  # Custom data added by our app.

    body = (
        '<h1>Hello %s at %s!</h1>\n'
        '<p>Our something is: %s</p>\n'
        ) % (user_agent, remote_ip, something)

    return {
        'body': body,
        'mimetype': 'text/html',  # This is actually the default
        'ttl': 30}                # Expire quickly from the browser cache!


if len(sys.argv) == 3:
    KITE_NAME, KITE_SECRET = sys.argv[1:3]
    if ':' in KITE_NAME:
        LOCAL_PORT, KITE_NAME = KITE_NAME.split(':', 1)
    else:
        LOCAL_PORT = 8076
    USERS[KITE_NAME] = KITE_SECRET
else:
    print("""\
Usage: scripts/hello.py KITENAME.pagekite.me KITE-SECRET

You can register your Pagekite account at https://pagekite.net/.
""")
    sys.exit(1)


# These things are added to the req_env dict passed to any dynamic URL
# handlers, and the global environment when running .py files from
# within the webroot. The demo app expects the following.
shared_req_env = {
    'something': 'My Custom Data',
    'app': {
         'uPK': myPageKiteSettings},
         'settings': {}}

# Create our HTTP server
httpd = HTTPD(KITE_NAME, WEB_ROOT, shared_req_env, myPageKiteSettings)

# Create our kite, directing any requests to the HTTP server. This is
# a "local" kite which means it also listens on a local port, not just
# the PageKite connection.
kite = LocalHTTPKite(int(LOCAL_PORT), KITE_NAME, KITE_SECRET,
                     handler=httpd.handle_http_request)

# Fly the kite, serve forever...
pk_control = uPageKite([kite], socks=[kite], uPK=myPageKiteSettings)
pk_control.run()
