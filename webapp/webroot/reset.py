# This file from the uPageKite distribution is placed in the Public Domain.
# Remix at will!

import json
import time
import machine

# FIXME: This would be a good place to demo HTTP authentication?

with open('bootstrap-config.json', 'rb') as fd:
  settings = json.loads(fd.read())

for k in ('key', 'ssid', 'kite_name', 'kite_secret'):
  if k in settings:
    del settings[k]

with open('/bootstrap-config.json', 'wb') as fd:
  fd.write(json.dumps(settings))

send_http_response("""\
<html><head>
  <link rel="icon" href="data:;base64,=">
  <style>%s</style>
  <title>upagekite: Resetting device</title>
</head><body>
  <h1>Configuration wiped.</h1>
  <p>Rebooting in 2 seconds...</p>
  <p>The device should broadcast its own WiFi network for reconfiguration soon.</p>
  <p>[ <a href="/">back to top</a> ]</p>
</body></html>
""" % (open('/webroot/default.css').read(),))

time.sleep(2)
machine.reset()
