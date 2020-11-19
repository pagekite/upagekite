# A dynamically generated web page.
#
# Note that the entire HTTP/1.0 response is generated here, including the
# HTTP/1.0 200 OK line and the HTTP headers.
#
try:
  import esp
  flash_size = '%d' % (esp.flash_size(),)
except:
  flash_size = 'unknown'

try:
  import machine
  mhz = '%.2fMhz' % (float(machine.freq()) / 1000000.0,)
except:
  mhz = 'unknown'

conn.reply(frame, ("""
HTTP/1.0 200 OK
Content-Type: text/html
Cache-Control: max-age=300

<html><head>
  <link rel="icon" href="data:;base64,=">
  <style>
%s
  </style>
  <title>upagekite: A Pythonic Index</title>
</head><body>
  <h1>Hello world!</h1>
  <p>This is <b>%s</b> at %s, you are %s</p>
  <p>I have a %s CPU and %s bytes of flash.</p>
  <p>See also: <a href="/hello.html">hello</a><p>
  <h3>Your request:</h3>
  <pre>%s</pre>
  <h3>Python state:</h3>
  <pre>Locals: %s</pre>
  <pre>WiFi SSID: %s</pre>
</body></html>
""") % (
     open('/bootstrap/webroot/default.css').read(),  # Inline the CSS
     kite.name,
     time.time(),
     frame.remote_ip,
     mhz,
     flash_size,
     str(frame.payload, 'latin-1').replace('<', '&lt;'),
     (', '.join(dir())).replace('<', '&lt;'),
     app['settings']['ssid']))
