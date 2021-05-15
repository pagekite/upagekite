# This file from the uPageKite distribution is placed in the Public Domain.
# Remix at will!
#
import sys
import time
import upagekite
import upagekite.httpd
from upagekite.proto import sleep_ms, ticks_ms
try:
  from boot import settings
except:
  try:
    from bootstrap import settings
  except:
    settings = {}


print("=2= Stage two compiled, here we go!")


if sys.platform == 'linux':
  HTTPD_PORT = 18080
  CDNS_PORT = 15353
else:
  HTTPD_PORT = 80
  CDNS_PORT = 53
  CAPTIVE_IP = '192.168.4.1'


@upagekite.httpd.async_url('/builtin')
async def slash_builtin(env):
  await sleep_ms(1)
  return {
    'mimetype': 'text/plain',
    'ttl': 60,
    'body': 'This is a built-in Python web endpoint\n'}


class MyProto(upagekite.uPageKiteDefaults):
  # Disable watchdog
  WATCHDOG_TIMEOUT = 45000

  trace = upagekite.uPageKiteDefaults.log
  debug = upagekite.uPageKiteDefaults.log
  info  = upagekite.uPageKiteDefaults.log
  error = upagekite.uPageKiteDefaults.log


class MyPageKite(upagekite.uPageKite):
  async def tick(self, *args, **kwargs):
    # Add a decoration to the tick log-line, run the standard tick.
    #kwargs['my'] = 'demo'
    await upagekite.uPageKite.tick(self, *args, **kwargs)
    # More periodic jobs here?


def captive_portal(env, httpd):
  try:
    import network, time
    wlan = network.WLAN(network.STA_IF)
    if not wlan.isconnected():
      print("=2= WiFi is down, bringing up captive portal.")
      wlan.active(False)
      wlan = network.WLAN(network.AP_IF)
      wlan.active(False)
      while not wlan.active():
        wlan.active(True)
        wlan.config(essid=MyProto.APPNAME)
        time.sleep(1)
      wlan.ifconfig((CAPTIVE_IP, '255.255.255.0', CAPTIVE_IP, CAPTIVE_IP))

      print("=2= AP config: %s" % (wlan.ifconfig(),))
      import upagekite.captive
      env['socks'].append(upagekite.captive.CDNS(CAPTIVE_IP, CDNS_PORT, MyProto))
      env['kites'] = []
      httpd.webroot = 'bootstrap/captive'
    del network
    del time
  except Exception as e:
    print('captive_portal() failed: %s' % e)


def get_upk():
  # These are things we want visible within the individual page scripts
  # run for dynamic HTTP requests. Setting this allows code to consult
  # global settings, which could become a security leak.
  env = {'proto': MyProto, 'settings': settings, 'kites': [], 'socks': []}

  httpd = upagekite.httpd.HTTPD(
    settings.get('kite_name', MyProto.APPNAME),
    'bootstrap/webroot',
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

  upk = MyPageKite(env['kites'], socks=env['socks'], proto=MyProto)
  env['upagekite'] = upk  # Expose to page logic
  return upk


from upagekite.proto import sleep_ms, ticks_ms
async def timer_latency_test():
  first_tick = ticks_ms() + 100
  counter = 0
  while True:
    next_tick = first_tick + (counter*100)
    await sleep_ms(max(1, next_tick - ticks_ms()))
    now = ticks_ms()
    if (now - next_tick > 25) or (counter % 10 == 9):
      print('Tick delayed by: %sms' % (now - next_tick))
    while next_tick <= now:
      counter += max(1, (now - next_tick) // 100)
      next_tick = first_tick + (counter*100)


if __name__ == "__main__":
  import gc
  from upagekite.proto import asyncio
  asyncio.get_event_loop().create_task(timer_latency_test())
  upk = get_upk()
  del get_upk
  del captive_portal
  gc.collect()
  upk.run()
