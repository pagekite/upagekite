# This file from the uPageKite distribution is placed in the Public Domain.
# Remix at will!
#
import gc
import sys
import time
import upagekite
import upagekite.httpd
import upagekite.websocket
from upagekite.proto import upk_open, ticks_ms, asyncio, fuzzy_sleep_ms

print("=2= Stage two compiled, here we go!")

try:
    with open('/bootstrap-config.json', 'rb') as fd:
        settings = json.loads(fd.read())
        print("=2= Loaded settings from /bootstrap-config.json")
except:
    settings = {}


if sys.platform == 'linux':
  HTTPD_PORT = 18080
  CDNS_PORT = 15353
else:
  HTTPD_PORT = 80
  CDNS_PORT = 53
  CAPTIVE_IP = '192.168.4.1'


@upagekite.httpd.url('/builtin', '/builtin/', _async=True)
async def slash_builtin(env):
  return {
    'body': 'This is a built-in Python web endpoint\n',
    'mimetype': 'text/plain; charset=us-ascii',
    'ttl': 60}


@upagekite.httpd.url('/builtin/big', '/builtin/big/')
def slash_builtin_big(env):
  chunks = 10240
  chunksize = 128  # Units of ten
  yield {
    'hdrs': {'Content-Length': 10*chunks*chunksize},
    'mimetype': 'text/plain; charset=us-ascii',
    'ttl': 60}
  bufr = bytearray('%8.8x %s\n' % (0, '0123456789' * (chunksize-1)))
  for i in range(0, chunks):
    bufr[:8] = b'%8.8x' % i
    yield bufr


@upagekite.httpd.async_url('/websocket', '/websocket/')
@upagekite.websocket.websocket('test')
async def ws_test(opcode, msg, conn, ws, first=False, eof=False, websocket=True):
  if not websocket:
    return {'body': upk_open('/webroot/websocket.html').read()}

  if first:
    await conn.send('Welcome, %s, to the Websocket Echo Chamber!' % conn.uid)
    await ws.broadcast('%s (%s) has joined us!' % (conn.uid, conn.remote_ip))
  elif msg and (opcode == upagekite.websocket.OPCODES.TEXT):
    await ws.broadcast('%s said: %s' % (conn.uid, msg))
  elif eof:
    await ws.broadcast('%s left.' % conn.uid)


# This demonstrates how to broadcast our log data to a websocket
LOG = []
async def ws_logger():
  global LOG
  while await fuzzy_sleep_ms(991):
    if LOG:
      lines, LOG = LOG, []
      await upagekite.websocket.ws_broadcast('test', '\n'.join(lines))
      del lines
      gc.collect()

def ws_log(msg):
  global LOG
  LOG.append('[%d] %s' % (ticks_ms(), msg))
  return upagekite.uPageKiteDefaults.log(msg)


class MyProto(upagekite.uPageKiteDefaults):
  # Disable watchdog
  WATCHDOG_TIMEOUT = None

  #trace = upagekite.uPageKiteDefaults.log  # Do not use ws_log!
  debug = ws_log
  error = ws_log
  info  = ws_log


def captive_portal(env, httpd):
  try:
    import network, time, machine, ubinascii
    uid = str(ubinascii.hexlify(machine.unique_id()), 'utf-8')
    essid = '%s-%s' % (MyProto.APPNAME, uid)
    wlan = network.WLAN(network.STA_IF)
    if not wlan.isconnected():
      print("=2= WiFi is down, bringing up captive portal: %s" % essid)

      while not wlan.active():
        wlan.active(True)
        env['wifi_scan'] = wlan.scan()
        time.sleep(0.25)
      wlan.active(False)

      wlan = network.WLAN(network.AP_IF)
      wlan.active(False)
      while not wlan.active():
        wlan.active(True)
        wlan.config(essid=essid)
        time.sleep(0.25)
      wlan.ifconfig((CAPTIVE_IP, '255.255.255.0', CAPTIVE_IP, CAPTIVE_IP))

      print("=2= AP config: %s" % (wlan.ifconfig(),))
      import upagekite.captive
      env['socks'].append(upagekite.captive.CDNS(CAPTIVE_IP, CDNS_PORT))
      env['kites'] = []
      httpd.webroot = '/bootstrap_live/captive'
    del network
    del time
  except Exception as e:
    print('captive_portal() failed: %s' % e)


def get_upk():
  # These are things we want visible within the individual page scripts
  # run for dynamic HTTP requests. Setting this allows code to consult
  # global settings, which could become a security leak.
  env = {'uPK': MyProto, 'settings': settings, 'kites': [], 'socks': []}

  httpd = upagekite.httpd.HTTPD(
    settings.get('kite_name', MyProto.APPNAME),
    '/bootstrap_live/webroot',
    {'app': env},
    MyProto)

  kite = upagekite.LocalHTTPKite(HTTPD_PORT,
    settings.get('kite_name'),
    settings.get('kite_secret'),
    httpd.handle_http_request)
  if settings.get('kite_name') and settings.get('kite_secret'):
    env['kites'].append(kite)
  if kite.fd:
    env['socks'].append(kite)

  if CDNS_PORT == 53:
    captive_portal(env, httpd)

  if env['kites']:
    print("=2= Launching uPageKite Hello World: http://%s" % kite.name)
  else:
    print("=2= Entering uPageKite event loop with no kites configured")
  print("=2= Press CTRL+C to abort and drop to REPL")
  print()
  time.sleep(2)

  upk = upagekite.uPageKite(env['kites'], socks=env['socks'], uPK=MyProto)
  env['upagekite'] = upk  # Expose to page logic
  return upk


if __name__ == "__main__":
  upk = get_upk()
  del get_upk
  del captive_portal
  asyncio.get_event_loop().create_task(ws_logger())
  gc.collect()
  upk.run()
