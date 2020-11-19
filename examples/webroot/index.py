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

conn.reply(frame, (
    'HTTP/1.0 200 OK\n'
    'Content-Type: text/html\n'
    '\n'
    '<h1>Hello world!</h1>\n'
    '<p>This is <b>%s</b> at %s, you are %s</p>\n'
    '<p>I have a %s CPU and %s bytes of flash.</p>\n'
    '<p>See also: <a href="/hello.html">hello</a><p>\n'
    '<h3>Your request:</h3>\n'
    '<pre>%s</pre>\n'
  ) % (
     kite.name,
     time.time(),
     frame.remote_ip,
     mhz,
     flash_size,
     str(frame.payload, 'latin-1').replace('<', '&lt;')))
