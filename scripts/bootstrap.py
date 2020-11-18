# This is a network bootstrapping script for ESP32 development
# Customize this:

import os
import ssl
import sys
import socket
import json

try:
  with open('bootstrap-config.json', 'rb') as fd:
    settings = json.loads(fd.read())
except:
  settings = {}

try:
  import network
  import time
  if settings.get('ssid') and settings.get('key'):
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(settings['ssid'], settings['key'])
    for i in range(0, 30):
      if wlan.isconnected():
        break
      time.sleep(1)
except:
  pass


try:
  from os import ilistdir
except ImportError:
  def ilistdir(path):
    return ((d, None, None) for d in os.listdir(path))


try:
  import machine
  import ubinascii
  HWID = str(ubinascii.hexlify(machine.unique_id()), 'latin-1')
except:
  HWID = 'unknown'


def http_get(proto, host, path):
  client = socket.socket()
  if ':' in host:
    hostname, port = host.split(':')
  else:
    port = 443 if (proto == 'https') else 80
    hostname = host
  client.connect(socket.getaddrinfo(hostname, int(port))[0][-1])
  if proto == 'https':
    client = ssl.wrap_socket(client)
  elif hasattr(client, 'makefile'):
    client = client.makefile("rwb", 0)
  if '%(hwid)s' in path:
    path = path % {'hwid': HWID}
  client.write(bytes(
    'GET %s HTTP/1.0\r\nHost: %s\r\n\r\n' % (path, host),
    'latin-1'))
  response = b''
  while len(response) < 64000:
      data = client.read(4096)
      if data:
          response += data
      else:
          break
  client.close()
  header, body = response.split(b'\r\n\r\n')
  header_lines = str(header, 'latin-1').splitlines()
  return (
    proto, host, path,
    header_lines[0],
    dict(l.split(': ', 1) for l in header_lines[1:]),
    body)


def make_parent(fn):
  parts = fn.split('/')
  parts.pop(-1)
  for i in range(0, len(parts)):
    try:
      os.mkdir('/'.join(parts[:i+1]))
    except OSError:
      pass


def rm_rf(fn):
  try:
    for sub in ilistdir(fn):
      if sub[0] not in ('.', '..'):
        rm_rf(fn + '/' + sub[0])
    os.rmdir(fn)
  except Exception as e:
    #print('%s: %s' % (fn, e))
    try:
      os.remove(fn)
    except Exception as e:
      pass  #print('%s: %s' % (fn, e))
  

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
  
  rm_rf('bootstrap.tmp')
  os.mkdir('bootstrap.tmp')
  for src, dest in bootstrap.get('mirror', {}).items():
    if dest in (True, 1):
      dest = src
    src_path = bootstrap['base_url_path'] + '/' + src
    _, _, _, result, _, data = http_get(proto, host, src_path)
    if ' 200 ' not in result:
      print('!!! ABORTING  %s: %s' % (src_path, result))
      return

    make_parent('bootstrap.tmp/' + dest)
    with open('bootstrap.tmp/' + dest, 'wb') as fd:
      fd.write(data)
    print(' *  %s: copied %d bytes => %s' % (src, len(data), dest))

  # FIXME: Run self-tests before switching? Can MicroPython do that?

  try:
    rm_rf('bootstrap.old')
    os.rename('bootstrap', 'bootstrap.old')
  except:
    pass
  os.rename('bootstrap.tmp', 'bootstrap')

  with open('bootstrap.json', 'wb') as fd:
    fd.write(bootstrap_json)
    print(' *  Updated local bootstrap.json')


def bootstrap():
  try:
    download_code(settings['src'])
  except Exception as e:
    print("!!! Network-based code update failed: %s" % e)

  print("=1= Chaining execution to bootstrap/stage_2 ...")
  if 'bootstrap' not in sys.path:
    sys.path.append('bootstrap')
  execfile('bootstrap/stage_2.py')


if __name__ == "__main__":
  bootstrap()
