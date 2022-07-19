# Copyright (C) 2021-2022, The Beanstalks Project ehf. and Bjarni R. Einarsson.
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option)
# any later version.
#
# Commercial licenses are for sale. See the files README.md and COPYING.txt
# for more details.
#
import gc
import os
import sys
import socket
import json


try:
  if execfile: pass
except NameError:
  def execfile(fn):
    exec(open(fn, 'r').read(), globals())

try:
  from os import ilistdir
except ImportError:
  def ilistdir(path):
    return ((d, None, None) for d in os.listdir(path))


def load_settings():
  try:
    with open('/bootstrap-config.json', 'rb') as fd:
      return json.loads(fd.read())
  except:
    return {}


def setting(key, val=None):
  settings = load_settings()
  if val is not None:
    settings[key] = val
    with open('/bootstrap-config.json', 'wb') as fd:
      fd.write(json.dumps(settings))
  return settings[key]


def rm_rf(fn):
  try:
    for sub in ilistdir(fn):
      if sub[0] not in ('.', '..'):
        rm_rf(fn + '/' + sub[0])
    os.rmdir(fn)
  except Exception as e:
    try:
      os.remove(fn)
    except Exception as e:
      print('WARNING: rm(%s) failed: %s' % (fn, e))


def mkdirexist(dn):
  parts = dn.split('/')
  for i in range(0, len(parts)):
    try:
      os.mkdir('/'.join(parts[:i+1]))
    except OSError:
      pass

def make_parent(fn):
  return mkdirexist(fn.rsplit('/', 1)[0])


def http_get(proto, host, path, fd=None):
  client = socket.socket()
  if ':' in host:
    hostname, port = host.split(':')
  else:
    port = 443 if (proto == 'https') else 80
    hostname = host
  client.connect(socket.getaddrinfo(hostname, int(port))[0][-1])
  if proto == 'https':
    import ssl
    client = ssl.wrap_socket(client)
  elif hasattr(client, 'makefile'):
    client = client.makefile("rwb", 0)
  if '%(hwid)s' in path:
    path = path % {'hwid': HWID}
  client.write(bytes(
    'GET %s HTTP/1.0\r\nHost: %s\r\n\r\n' % (path, host),
    'latin-1'))

  body = client.read(4096)
  size = len(body)
  header, body = body.split(b'\r\n\r\n', 1)
  header_lines = str(header, 'latin-1').splitlines()
  if fd:
      fd.write(body)
      while True:
          body = client.read(4096)
          if body:
              size += len(body)
              fd.write(body)
          else:
              break
  else:
      while len(body) < 64000:
          data = client.read(4096)
          if data:
              body += data
          else:
              break

  client.close()
  return (
    proto, host, path,
    header_lines[0],
    dict(l.split(': ', 1) for l in header_lines[1:]),
    (size if fd else body))


def bootstrap_2():
  print("=1= Chaining execution to bootstrap_live/stage_2 ...")
  if '/bootstrap_live' not in sys.path:
    sys.path.append('/bootstrap_live')
  return execfile('/bootstrap_live/stage_2.py')


def bootstrap_1(settings, download=True):
  try:
    import machine
    import ubinascii
    HWID = str(ubinascii.hexlify(machine.unique_id()), 'latin-1')
  except:
    HWID = 'unknown'

  def download_code(url):
    proto, host, path = url.replace('://', '/').split('/', 2)
    proto, host, path, result, headers, bootstrap_json = http_get(proto, host, '/'+path)
    if ' 200 ' not in result:
      print('!!! ABORTING  %s://%s%s: %s' % (proto, host, path, result))
      return

    bootstrap = json.loads(bootstrap_json)
    version = bootstrap.get('version', 0)
    print('=1= Bootstrap .json v%d is %d bytes, date %s' % (
      version,
      len(bootstrap_json),
      headers.get('Last-Modified', 'unknown')))

    if version:
      try:
        current = json.loads(open('bootstrap.json', 'rb').read())
        if current.get('version', -1) >= version:
          print('=1= Bootstrap is unchanged, we are done for now.')
          return
      except:
        pass

    rm_rf('bootstrap_old')
    rm_rf('bootstrap.tmp')
    os.mkdir('bootstrap.tmp')
    for src, dest in bootstrap.get('mirror', {}).items():
      if dest in (True, 1):
        dest = src
      make_parent('bootstrap.tmp/' + dest)
      with open('bootstrap.tmp/' + dest, 'wb') as fd:
        src_path = bootstrap['base_url_path'] + '/' + src
        try:
          _, _, _, result, _, size = http_get(proto, host, src_path, fd)
        except Exception as e:
          result = ('Exception(%s)' % e)
        if ' 200 ' not in result:
          print('!!! ABORTING  %s: %s' % (src_path, result))
          return

        print(' *  %s: copied %d bytes => %s' % (src, size, dest))

    # FIXME: Run self-tests before switching? Can MicroPython do that?

    try:
      os.rename('bootstrap_live', 'bootstrap_old')
    except:
      pass
    os.rename('bootstrap.tmp', 'bootstrap_live')

    with open('bootstrap.json', 'wb') as fd:
      fd.write(bootstrap_json)
      print(' *  Updated local bootstrap.json')

  def wifi_up():
    try:
      import network
      import time
      if settings.get('ssid') and settings.get('key'):
        network.WLAN(network.AP_IF).active(False)
        wlan = network.WLAN(network.STA_IF)
        wlan.active(False)
        time.sleep(1)
        wlan.active(True)
        wlan.connect(settings['ssid'], settings['key'])
        print('=== Connecting to WiFi: %s' % (settings['ssid'],))
        for i in range(0, 60):
          if wlan.isconnected():
            break
          time.sleep(1)
        ifc = wlan.ifconfig()
        print('=== Connected with IP: %s' % (ifc[0]))
    except Exception as e:
      print('!!! Failed to bring up WiFi: %s' % e)

  try:
    wifi_up()
    if download and 'src' in settings:
      download_code(settings['src'])
  except Exception as e:
    print("!!! Network-based code update failed: %s" % e)


def run():
  bootstrap_1(load_settings())
  gc.collect()
  bootstrap_2()


if __name__ == "__main__":
  del run
  del setting
  bootstrap_1(load_settings())
  del load_settings
  del bootstrap_1
  del http_get
  del rm_rf
  del make_parent
  del mkdirexist
  gc.collect()
  bootstrap_2()
