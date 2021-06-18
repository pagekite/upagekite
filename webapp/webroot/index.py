# This file from the uPageKite distribution is placed in the Public Domain.
# Remix at will!

import gc

flash_size = 'unknown'
try:
  import esp
  flash_size = '%d' % (esp.flash_size(),)
except:
  pass

mhz = 'unknown'
try:
  import machine
  mhz = '%.2fMhz' % (float(machine.freq()) / 1000000.0,)
except:
  pass


def say_something(what, foobar='okay'):
  print('Postponed %s (%s)' % (what, foobar))

# This illustrates how to queue up an action to run after we have
# returned a result to the user; this improves response times, but
# also unblocks the main event loop in case other tasks have become
# (over)due.
postpone_action(say_something, 'hello world', foobar='hooray')


# Most of the arguments could be omitted, they have sensible defaults.
send_http_response(
  ttl=120, code=200, mimetype='text/html; charset=utf-8',
  body=("""\
<html><head>
  <link rel="icon" href="data:;base64,=">
  <style>
%s
  </style>
  <title>upagekite: A Pythonic Index</title>
</head><body>
  <h1>Hello world!</h1>
  <p>This is <b>%s</b> at %s, you are %s</p>
  <p>I have a %s CPU and %s bytes of flash, %s bytes of free RAM.</p>
  <p>
    See also:
    <a href="/hello/">hello</a>,
    <a href="/websocket/">websocket</a>,
    <a href="/post.py">post</a>,
    <a onclick='return confirm("Are you sure?");' href="/reboot.py">reboot</a>,
    <a onclick='return confirm("Are you sure?");' href="/reset.py">reset</a>
  <p>
  <h3>Your request:</h3>
  <p><tt>%s</tt></p>
  <h3>Python state:</h3>
  <p><tt>Locals: %s</tt></p>
  <p><tt>WiFi SSID: %s</tt></p>
</body></html>
""") % (
  open('/webroot/default.css').read(),  # Inline the CSS
  kite.name,
  time.time(),
  frame.remote_ip,
  mhz,
  flash_size,
  gc.mem_free() if hasattr(gc, 'mem_free') else 'unknown',
  ('%s' % http_headers).replace('<', '&lt;'),
  (', '.join(dir())).replace('<', '&lt;'),
  app.get('settings', {}).get('ssid', 'unknown')))

