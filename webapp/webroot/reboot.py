# This file from the uPageKite distribution is placed in the Public Domain.
# Remix at will!

import time

from upagekite.web import access_requires


if not req_env.is_local:
  access_requires(req_env,
    auth='basic',
    auth_check=lambda m,up: up == ('root', 'testing'))


send_http_response("""\
<html><head>
  <meta http-equiv="refresh" content="90; url=/">
  <link rel="icon" href="data:;base64,=">
  <style>
%s
  </style>
  <title>upagekite: Rebooting!</title>
  <script>
    var count = 90;
    setInterval(function() {
      document.getElementById('t').innerHTML = (count-- + 's');
    }, 1000);
  </script>
</head><body>
  <h1>Rebooting!</h1>
  <p>Rebooting in 2 seconds... page refresh in <span id=t>60s</span>.</p>
  <p>[ <a href="/">back to top</a> ]</p>
</body></html>
""" % (open('/webroot/default.css').read(),))

time.sleep(2)

import machine
machine.reset()
