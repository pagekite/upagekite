# This file from the uPageKite distribution is placed in the Public Domain.
# Remix at will!

import re

# If the user typed in an IP address, keep it.
hostname = app['uPK'].APPNAME
if re.match('^[0123456789\.]+$', http_headers.get('Host', '')):
  hostname = http_headers['Host']

send_http_response(
  code=307,
  ttl=1,
  hdrs={'Location': 'http://%s/setup/' % hostname})
