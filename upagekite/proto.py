# Copyright (C) 2020-2022, The Beanstalks Project ehf. and Bjarni R. Einarsson.
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option)
# any later version.
#
# Commercial licenses are for sale. See the files README.md and COPYING.txt
# for more details.
#
### # #
#
# A low-level PageKite protocol implementation.
#
# Note that some of this code is not currently thread-safe, in particular
# the uPageKiteDefaults.connect() method should not run be run concurrently
# with the same set of Kite objects.
#
import gc
import random
import re
import sys
import struct
import time
import select
from hashlib import sha1
from struct import unpack


# This is also used by setup.py
UPAGEKITE_VERSION = '0.3.1'

# This is a cache of DNS hints we have recived from the network.
_DNS_HINTS = {}

# A global counter for bytes we've sent over the network
SENT_COUNTER = 0
SENT_DELAYS = 0

# Prefixes to search when trying to open() files from within the webapp.
APP_ROOT_PREFIXES = ('/bootstrap_live', '/bootstrap', '')


try:
    import uasyncio as asyncio
    IS_MICROPYTHON = True
except ImportError:
    import asyncio
    IS_MICROPYTHON = False

try:
    from builtins import PermissionError
except ImportError:
    class PermissionError(OSError):
        pass

try:
    SELECT_POLL_IN = (select.POLLPRI | select.POLLIN)
except AttributeError:
    SELECT_POLL_IN = (select.POLLIN)

try:
    from sys import print_exception as print_exc
except ImportError:
    from traceback import print_exc as _print_exc
    def print_exc(e):
      return _print_exc()

try:
  from time import ticks_ms
except ImportError:
  def ticks_ms():
    return int(time.time() * 1000)

try:
  from os import urandom as random_bytes
except ImportError:
  def random_bytes(length):
    return bytes(random.getrandbits(8) for r in range(0, length))

try:
  from os import ilistdir
except ImportError:
  from os import listdir
  def ilistdir(path):
    return ((d, None, None) for d in listdir(path))

try:
  import ubinascii
  def sha1hex(data):
    return str(ubinascii.hexlify(
      sha1(bytes(data, 'latin-1')).digest()), 'latin-1')
except ImportError:
  def sha1hex(data):
    return sha1(bytes(data, 'latin-1')).hexdigest()

try:
    import ussl as ssl
except ImportError:
    try:
        import ssl
    except ImportError:
        ssl = False

try:
    from utime import sleep_ms as real_sleep_ms
    from uasyncio import sleep_ms
except ImportError:
    def real_sleep_ms(ms):
        time.sleep(ms/1000.0)
    async def sleep_ms(ms):
        await asyncio.sleep(ms/1000.0)

try:
  import usocket as socket
  IOError = OSError
  async def sock_connect_stream(uPK, addr, ssl_wrap=False, timeouts=(20, 300)):
    if uPK.trace:
      uPK.trace('>>connect(%s, ssl_wrap=%s)' % (addr, ssl_wrap))
    s = socket.socket()
    try:
      s.settimeout(timeouts[0])
      await fuzzy_sleep_ms()
      s.connect(addr)
      s.settimeout(timeouts[1])
      await fuzzy_sleep_ms()
      if ssl_wrap:
        uPK.GC_COLLECT()
        await fuzzy_sleep_ms(30)
        return (s, ssl.wrap_socket(s))
      await fuzzy_sleep_ms()
      return (s, s)
    except:
      s.close()
      raise
except ImportError:
  import socket
  IOError = IOError
  async def sock_connect_stream(uPK, addr, ssl_wrap=False, timeouts=(20, 300)):
    if uPK.trace:
      uPK.trace('>>connect(%s, ssl_wrap=%s)' % (addr, ssl_wrap))
    s = socket.socket()
    s.settimeout(timeouts[0])
    await fuzzy_sleep_ms()
    s.connect(addr)
    s.settimeout(timeouts[1])
    if ssl_wrap:
      await fuzzy_sleep_ms(30)
      s = ssl.wrap_socket(s)
    await fuzzy_sleep_ms()
    return (s, s.makefile("rwb", 0))


def upk_open(path, mode='r'):
  ose = ''
  tried = []
  for root in APP_ROOT_PREFIXES:
    try:
      tried.append(root + path)
      return open(root + path, mode)
    except OSError as e:
      ose = e
  raise OSError(str(ose) + (' tried: %s' % ', '.join(tried)))


class RejectedError(ValueError):
  pass

class EofTunnelError(IOError):
  pass

class EofStream(IOError):
  pass


async def fuzzy_sleep_ms(ms=0):
  real_sleep_ms(1)
  if ms > 1:
    await sleep_ms(ms-1)
  return max(ms, 1)


class Kite:
  def __init__(self, name, secret, proto='http', handler=None):
    self.pproto = self.proto = proto
    if self.proto[:3] == 'tls':
      self.proto = 'https' + self.proto[3:]
    elif self.proto[:3] == 'ssh':
      self.proto = 'raw' + self.proto[3:]

    self.name = name
    self.secret = secret
    self.challenge = ''
    self.handler = handler

  def __str__(self):
    return '%s://%s' % (self.pproto, self.name)


class Frame:
  def __init__(self, uPK, data=None, headers=None, payload=None, cid=''):
    self.uPK = uPK
    self.cid = '%s' % (cid,)
    if data:
      hdr_len = data.index(b'\r\n\r\n')
      hdr = str(data[:hdr_len], 'latin-1')
      self.payload = data[hdr_len+4:]
      self.headers = dict(ln.strip().split(': ', 1)
        for ln in hdr.splitlines())
    else:
      self.headers = headers
      self.payload = payload

  eof = property(lambda s: s.headers.get('EOF', ''))
  sid = property(lambda s: s.headers.get('SID'))
  uid = property(lambda s: s.cid + s.headers.get('SID'))
  tls = property(lambda s: s.headers.get('RTLS'))
  host = property(lambda s: s.headers.get('Host'))
  port = property(lambda s: s.headers.get('Port'))
  proto = property(lambda s: s.headers.get('Proto'))
  remote_ip = property(lambda s: s.headers.get('RIP'))
  ping = property(lambda s: s.headers.get('PING'))


class uPageKiteDefaults:
  APPNAME = 'uPageKite'
  APPURL = 'https://github.com/pagekite/upagekite'
  APPVER = UPAGEKITE_VERSION+'u'
  # Warning: Micropython does not like large regexps, which is why this
  #          one is annoyingly imprecise.
  PARSE_HTTP_HEADERS = re.compile(
    '^(Auth'
    '|Con[nt]'
    '|Cook'
    '|Host'
    '|Orig'
    '|Sec-Web'
    '|Upgrade'
    '|User-Agent)[^:]*:')
  FE_NAME = 'fe4_100.b5p.us'  # pagekite.net IPv4 pool for pagekite.py 1.0.0
  FE_PORT = 443
  DDNS_URL = ('http', 'up.pagekite.net',  # FIXME: https if enough RAM?
              '/?hostname=%(domain)s&myip=%(ips)s&sign=%(sign)s')
  TOKEN_LENGTH = 36
  WITH_SSL = (ssl is not False)

  # Default HTTP Security headers
  HTTP_CONTENT_SECURITY_POLICY = "default-src 'self' 'unsafe-inline' 'unsafe-eval'"
  HTTP_REFERRER_POLICY = 'same-origin'
  HTTP_CORS_ORIGIN = None
  HTTP_CORS_METHODS = None
  HTTP_CORS_HEADERS = None

  # These are used to compensate for Micropython/ESP32 having
  # an overly dumb DNS implementation.
  FE_HINT_NAME = 'fe.b5p.us'
  FE_HINT_URL = ('http', 'pagekite.net', '/logs/relays.txt')

  TICK_INTERVAL = 16
  MIN_CHECK_INTERVAL = 16
  MAX_CHECK_INTERVAL = 900
  WATCHDOG_TIMEOUT = 60000
  SOCKET_TIMEOUTS = (5, 60)  # (connect, data) timeouts, in seconds
  TUNNEL_TIMEOUT = 240
  MAX_POST_BYTES = 64 * 1024
  RANDOM_PING_VALUES = False

  # These values are critical magic under MicroPython - if the balance
  # is wrong, we get garbage reads from our tunnel socket or run out of
  # memory on the ESP32. In particular, the send window may not be much
  # larger than FILE_READ_BYTES; so those must be raised together and
  # that will in turn effect RAM usage. This limits performance.
  SEND_WINDOW_BYTES = (1499 if IS_MICROPYTHON else 112909)
  FILE_READ_BYTES = (1499 if IS_MICROPYTHON else 112909) - 64
  MS_DELAY_PER_BYTE = (0.025 if IS_MICROPYTHON else 0.005)

  WEBSOCKET_MASK = lambda: b'\0\0\0\0'
  WEBSOCKET_MAX_CONNS = (5 if IS_MICROPYTHON else 100)

  # Set to lambda: None to disable
  GC_COLLECT = (gc.collect if IS_MICROPYTHON else (lambda: None))
  trace = False  # Set to log in subclass to enable noise
  debug = False  # Set to log in subclass to enable noise
  info = False   # Set to log in subclass to enable noise
  error = False  # Set to log in subclass to enable noise

  @classmethod
  def log(cls, message):
    print('[%d] %s' % (ticks_ms(), message))

  @classmethod
  def addr_to_quad(cls, addr):
    if isinstance(addr, tuple):
      return addr[0]
    if isinstance(addr, bytearray):
      return '.'.join('%d' % b for b in unpack('8B', addr)[4:])
    return addr

  @classmethod
  def make_random_secret(cls, salt=''):
    # We do not know how good our randomness is; if it is really good, then
    # the salt and platform and time don't matter. If it is bad, then we
    # hope xor'ing against the SHA1 of secret values will compensate.
    salt = sha1(bytes(
        '%s' % ((ticks_ms(), sys.platform, sys.implementation, salt),),
        'latin-1'
      )).digest()
    rs = bytes((b^salt[i]) for i, b in enumerate(random_bytes(16)))
    if cls.trace:
      cls.trace('Random secret: %s' % rs)
    return rs

  @classmethod
  async def network_send_sleep(uPK, sent):
    global SENT_COUNTER
    global SENT_DELAYS

    SENT_COUNTER += sent
    if SENT_COUNTER > 100*1024*1024:
      SENT_COUNTER = SENT_DELAYS = 0

    sleep_time = 5 + int((SENT_COUNTER * uPK.MS_DELAY_PER_BYTE) - SENT_DELAYS)
    SENT_DELAYS += sleep_time
    await fuzzy_sleep_ms(sleep_time)

  @classmethod
  async def check_fe_hint_url(cls):
    global _DNS_HINTS
    result = None
    try:
      proto, host, path = cls.FE_HINT_URL
      result = await cls.http_get(proto, host, path, dns_hints=True)
      if ' 200 ' not in result[0]:
        raise Exception('Failed')
      cls.scan_for_dns_hints(str(result[-1] or '', 'latin-1').splitlines())
      if cls.debug:
        cls.debug('Updated DNS hints: %s' % (_DNS_HINTS))
    except Exception as e:
      if cls.error:
        cls.error(
          'Failed to update DNS hints: %s => (%s, %s)'
          % (cls.FE_HINT_URL, result, e))

  @classmethod
  def scan_for_dns_hints(cls, lines):
    global _DNS_HINTS
    for line in lines:
      if 'X-DNS: ' == line[:7]:
        xdns, host, ips = line.split(' ', 2)
        ips = [i.strip() for i in ips.split(',')]
        if host and ips:
          _DNS_HINTS[host] = ips

  @classmethod
  async def http_get(cls, proto, http_host, path,
                     addr=None, atonce=1024, maxread=8196, dns_hints=False):
    if addr is None:
      addr = http_host
    if hasattr(addr, 'split'):
      if ':' in addr:
        hostname, port = addr.split(':')
      else:
        port = 443 if (proto == 'https') else 80
        hostname = addr
      await fuzzy_sleep_ms()
      addr = socket.getaddrinfo(hostname, int(port))[0][-1]

    conn = None
    try:
      await fuzzy_sleep_ms()
      t0 = ticks_ms()
      cfd, conn = await sock_connect_stream(cls, addr,
        ssl_wrap=(proto == 'https'),
        timeouts=cls.SOCKET_TIMEOUTS)
      await cls.send(conn,
        'GET %s HTTP/1.0\r\nHost: %s\r\n\r\n' % (path, http_host))

      t1 = ticks_ms()
      response = b''
      while len(response) < maxread:
        try:
          await fuzzy_sleep_ms()
          data = conn.read(atonce)
          response += data
        except:
          data = None
        if not data:
          break
      conn.close()
      t2 = ticks_ms()

      try:
        header, body = response.split(b'\r\n\r\n', 1)
      except ValueError:
        header = response
        body = ''
      header_lines = (str(header, 'latin-1') or '\n').splitlines()
      if dns_hints:
        cls.scan_for_dns_hints(header_lines)
      return (
        header_lines[0],
        dict(l.split(': ', 1) for l in header_lines[1:]),
        t1-t0, t2-t1, body)
    finally:
      try:
        conn.close()
      except:
        pass

  @classmethod
  async def get_kite_addrinfo(cls, kite):
    try:
      await fuzzy_sleep_ms(5)
      return socket.getaddrinfo(kite.name, cls.FE_PORT, socket.AF_INET, socket.SOCK_STREAM)
    except IOError:
      return []

  @classmethod
  async def get_relays_addrinfo(cls):
    global _DNS_HINTS
    addrs = []
    if cls.FE_NAME:
      await fuzzy_sleep_ms(5)
      try:
        addrs = socket.getaddrinfo(cls.FE_NAME, cls.FE_PORT, socket.AF_INET, socket.SOCK_STREAM)
      except IOError:
        pass
      for name in (cls.FE_NAME, cls.FE_HINT_NAME):
        for ip in _DNS_HINTS.get(name, []):
          await fuzzy_sleep_ms()
          try:
            ai = socket.getaddrinfo(ip, cls.FE_PORT, socket.AF_INET, socket.SOCK_STREAM)
            addrs.extend(ai)
          except IOError:
            pass
    return addrs

  @classmethod
  async def ping_relay(cls, relay_addr, bias=1.0):
    if cls.RANDOM_PING_VALUES:
      return random.randint(100, 300)
    try:
      l1, hdrs, t1, t2, body = await cls.http_get(
        'http', 'ping.pagekite', '/ping', relay_addr,
        atonce=250, dns_hints=True)

      elapsed = t1 + t2
      biased = int(float(elapsed) * bias)
      if 'X-PageKite-Overloaded' in hdrs:
        biased += 250 if (bias == 1.0) else 50

      if cls.debug:
        cls.debug('Ping %s ok: %dms (~%dms)' % (relay_addr, elapsed, biased))
      return biased
    except (IOError, OSError) as e:
      if cls.info:
        cls.info('Ping %s failed: %s' % (relay_addr, e))
      return 99999

  @classmethod
  def sync_send(cls, conn, data):
    data = bytes(data, 'utf-8') if isinstance(data, str) else data
    if cls.trace:
      cls.trace(']>[%d] %s' % (len(data), data[:24]))
    for chunk in range(0, len(data), cls.SEND_WINDOW_BYTES):
      conn.write(data[chunk:chunk+cls.SEND_WINDOW_BYTES])
    if hasattr(conn, 'flush'):
      conn.flush()

  @classmethod
  async def send(cls, conn, data):
    data = bytes(data, 'utf-8') if isinstance(data, str) else data
    for chunk in range(0, len(data), cls.SEND_WINDOW_BYTES):
      # FIXME: Make this actually async!
      conn.write(data[chunk:chunk+cls.SEND_WINDOW_BYTES])
      await cls.network_send_sleep(min(len(data), cls.SEND_WINDOW_BYTES))
    if hasattr(conn, 'flush'):
      conn.flush()
    if cls.trace:
      cls.trace('>>[%d] %s' % (len(data), data[:24]))

  @classmethod
  def fmt_chunk(cls, data):
    data = bytes(data, 'utf-8') if isinstance(data, str) else data
    return b'%x\r\n%s' % (len(data), data)

  @classmethod
  def fmt_data(cls, frame, data):
    return cls.fmt_chunk(b'SID: %s\r\n\r\n%s'% (
      bytes(frame.sid, 'latin-1'),
      bytes(data, 'utf-8') if isinstance(data, str) else data))

  @classmethod
  def fmt_eof(cls, frame):
    return cls.fmt_chunk(b'SID: %s\r\nEOF: 1WR\r\n\r\n' % (
      bytes(frame.sid, 'latin-1'),))

  @classmethod
  def fmt_pong(cls, pong):
    return cls.fmt_chunk(b'NOOP: 1\r\nPONG: %s\r\n\r\n!' % (
      bytes(pong, 'latin-1') if isinstance(pong, str) else pong,))

  @classmethod
  def fmt_ping(cls):
    return cls.fmt_chunk(b'NOOP: 1\r\nPING: %.2f\r\n\r\n!' % (time.time(),))

  @classmethod
  async def read_http_header(cls, conn):
    header = bytes()
    read_bytes = 1
    await fuzzy_sleep_ms(20)
    while header[-4:] != b'\r\n\r\n':
      byte = conn.read(1)
      if byte in (b'', None):
        raise EofTunnelError()
      header += byte
    if cls.trace:
      cls.trace('<< %s' % header)
    await fuzzy_sleep_ms()
    return header

  @classmethod
  async def read_chunk(cls, conn):
    hdr = b''
    try:
      while not hdr.endswith(b'\r\n') and len(hdr) < 10:
        byte = conn.read(1)
        if byte in (b'', None):
          raise EofTunnelError()
        hdr += byte

      chunk_len = int(str(hdr, 'latin-1').strip(), 16)
      payload = b''
      while len(payload) < chunk_len:
        payload += conn.read(chunk_len - len(payload))

      if len(payload) != chunk_len:
        raise EofTunnelError(
          'Read size mismatch: %s != %s' % (len(payload), chunk_len))
      if cls.trace:
        cls.trace('<<[%d] %s %s' % (len(payload)+len(hdr), hdr, payload[:40]))

      return payload
    except (UnicodeError, ValueError):
      if cls.debug:
        cls.debug('Invalid chunk header: %s' % hdr)
      raise EofTunnelError()
    except OSError:
      raise EofTunnelError()

  @classmethod
  def sign(cls, secret, payload, salt=None, ts=None, length=None):
    if not salt:
      salt = '%x' % struct.unpack('I', cls.make_random_secret()[:4])
    if not length:
      length = cls.TOKEN_LENGTH
    if ts:
      salt = 't' + salt[1:]
      payload += '%x' % int(ts / 600)
    return (
      salt[0:8] +
      sha1hex(secret + payload + salt[0:8])[:length-8])

  @classmethod
  def x_pagekite(cls, relay_addr, kites, global_secret):
    reqs = []
    for kite in kites:
      client_token = sha1hex(
          '%s/%s/%s' % (global_secret, relay_addr, kite.secret)
        )[:cls.TOKEN_LENGTH]
      server_token = kite.challenge or ''
      data = '%s:%s:%s:%s' % (kite.proto, kite.name, client_token, server_token)
      sign = cls.sign(kite.secret, data)
      reqs.append('X-PageKite: %s:%s\r\n' % (data, sign))
    return ''.join(reqs)

  @classmethod
  def parse_challenge(cls, challenge, kites):
    ok = []
    rejected = []
    needsign = []
    for line in str(challenge, 'latin-1').splitlines():
      if line.startswith('X-PageKite-SignThis:'):
        parts = line.split(':')
        proto = parts[1].strip()
        kitename = parts[2]
        for kite in kites:
          if kite.name == kitename and kite.proto == proto:
            kite.challenge = parts[4]  # FIXME: Not thread safe!
            needsign.append(kite)
      elif line.startswith('X-PageKite-OK:'):
        ok.append(':'.join(line.split(':')[:3]))
      elif line.startswith('X-PageKite-Reject'):
        rejected.append(':'.join(line.split(':')[:3]))
      elif line.startswith('X-PageKite-Duplicate'):
        rejected.append(':'.join(line.split(':')[:3]))
      else:
        pass  # Parse the other lines too?
    return ok, needsign, rejected

  @classmethod
  async def connect(cls, relay_addr, kites, global_secret):
    if cls.debug:
      cls.debug('Flying %s via %s' % (
        ', '.join(str(k) for k in kites), relay_addr))

    for kite in kites:
      kite.challenge = ''

    # Connect, get fresh challenges
    cfd, conn = await sock_connect_stream(cls, relay_addr,
      ssl_wrap=cls.WITH_SSL,
      timeouts=cls.SOCKET_TIMEOUTS)
    await cls.send(conn, (
        'CONNECT PageKite:1 HTTP/1.0\r\n'
        'X-PageKite-Features: AddKites\r\n'
        'X-PageKite-Version: %s\r\n'
        '%s\r\n'
      ) % (
        cls.APPVER,
        cls.x_pagekite(relay_addr, kites, global_secret)))

    # Make sense of it...
    challenge = await cls.read_http_header(conn)
    ok, needsign, rejected = cls.parse_challenge(challenge, kites)
    if rejected:
      conn.close()
      raise RejectedError(', '.join(rejected))

    if needsign:
      await cls.send(conn, cls.fmt_chunk((
          'NOOP: 1\r\n'
          '%s\r\n'
        ) % (
          cls.x_pagekite(relay_addr, needsign, global_secret))))
      challenge = await cls.read_chunk(conn)
      ok2, needsign, rejected = cls.parse_challenge(challenge, kites)
      ok += ok2
      if rejected or needsign:
        conn.close()
        raise RejectedError(', '.join(rejected + needsign))

    if not ok:
      conn.close()
      raise RejectedError('No requests accepted, is this really a relay?')

    if cls.info:
      cls.info('Connected to %s' % (relay_addr,))

    await fuzzy_sleep_ms()
    return cfd, conn

  @classmethod
  async def update_dns(cls, relay_ip, kites):
    proto, host, path_fmt = cls.DDNS_URL
    errors = 0
    for kite in kites:
      try:
        payload = '%s:%s' % (kite.name, relay_ip)
        l1, hdrs, t1, t2, body = await cls.http_get(
          proto, host, path_fmt % {
            'domain': kite.name,
            'sign': cls.sign(kite.secret, payload, length=100),
            'ips': relay_ip})
        if not (body.startswith(b'good') or body.startswith(b'nochg')):
          errors += 1
      except Exception as e:
        body = 'failed, %s' % e
        errors += 1
      if cls.debug:
        if not isinstance(body, str):
          body = str(body, 'latin-1')
        cls.debug('DNS update %s to %s: %s' % (
          kite.name, relay_ip, body.strip()))

    return (errors == 0)
