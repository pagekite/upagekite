# Copyright (C) 2020, The Beanstalks Project ehf. and Bjarni R. Einarsson.
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
import re
import sys
import struct
import time
import select
from hashlib import sha1
from struct import unpack

try:
  from time import ticks_ms
except ImportError:
  def ticks_ms():
    return int(time.time() * 1000)

try:
  from os import urandom as random_bytes
except ImportError:
  import random
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
  import usocket as socket
  IOError = OSError
  def sock_connect_stream(proto, addr, ssl_wrap=False, timeouts=(20, 300)):
    if proto.trace:
      proto.trace('>>connect(%s, ssl_wrap=%s)' % (addr, ssl_wrap))
    s = socket.socket()
    s.settimeout(timeouts[0])
    s.connect(addr)
    s.settimeout(timeouts[1])
    if ssl_wrap:
      gc.collect()
      return (s, ssl.wrap_socket(s))
    return (s, s)
except ImportError:
  import socket
  def sock_connect_stream(proto, addr, ssl_wrap=False, timeouts=(20, 300)):
    if proto.trace:
      proto.trace('>>connect(%s, ssl_wrap=%s)' % (addr, ssl_wrap))
    s = socket.socket()
    s.settimeout(timeouts[0])
    s.connect(addr)
    s.settimeout(timeouts[1])
    if ssl_wrap:
      s = ssl.wrap_socket(s)
    return (s, s.makefile("rwb", 0))


class RejectedError(ValueError):
  pass

class EofTunnelError(IOError):
  pass


class Kite:
  def __init__(self, name, secret, proto='http', handler=None):
    self.proto = proto
    self.name = name
    self.secret = secret
    self.challenge = ''
    self.handler = handler

  def __str__(self):
    return '%s://%s' % (self.proto, self.name)


class Frame:
  def __init__(self, data=None, headers=None, payload=None):
    if data:
      hdr_len = data.index(b'\r\n\r\n')
      hdr = str(data[:hdr_len], 'latin-1')
      self.payload = data[hdr_len+4:]
      self.headers = dict(ln.strip().split(': ', 1)
        for ln in hdr.splitlines())
    else:
      self.headers = headers
      self.payload = payload

  sid = property(lambda s: s.headers.get('SID'))
  host = property(lambda s: s.headers.get('Host'))
  port = property(lambda s: s.headers.get('Port'))
  proto = property(lambda s: s.headers.get('Proto'))
  remote_ip = property(lambda s: s.headers.get('RIP'))
  ping = property(lambda s: s.headers.get('PING'))


class uPageKiteDefaults:
  APPNAME = 'uPageKite'
  APPURL = 'https://github.com/pagekite/upagekite'
  APPVER = '0.0.1u'
  PARSE_HTTP_HEADERS = re.compile('^(Host|User-Agent|Cookie):')
  FE_NAME = 'fe4_100.b5p.us'  # pagekite.net IPv4 pool for pagekite.py 1.0.0
  FE_PORT = 443
  DDNS_URL = ('http', 'up.pagekite.net',  # FIXME: https if enough RAM?
              '/?hostname=%(domain)s&myip=%(ips)s&sign=%(sign)s')
  TOKEN_LENGTH = 36
  WITH_SSL = (ssl is not False)

  TICK_INTERVAL = 16
  MIN_CHECK_INTERVAL = 16
  MAX_CHECK_INTERVAL = 900
  WATCHDOG_TIMEOUT = 5000

  trace = False  # Set to log in subclass to enable noise
  debug = False  # Set to log in subclass to enable noise
  info = False   # Set to log in subclass to enable noise
  error = False  # Set to log in subclass to enable noise

  @classmethod
  def log(cls, message):
    print('[%x] %s' % (int(time.time()), message))

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
  def http_get(cls, proto, http_host, path, addr=None, atonce=1024, maxread=8196):
    if addr is None:
      addr = http_host
    if hasattr(addr, 'split'):
      if ':' in addr:
        hostname, port = addr.split(':')
      else:
        port = 443 if (proto == 'https') else 80
        hostname = addr
      addr = socket.getaddrinfo(hostname, int(port))[0][-1]

    t0 = ticks_ms()
    cfd, conn = sock_connect_stream(cls, addr, ssl_wrap=(proto == 'https'))
    cls.send_raw(conn,
      'GET %s HTTP/1.0\r\nHost: %s\r\n\r\n' % (path, http_host))

    t1 = ticks_ms()
    response = b''
    while len(response) < maxread:
      try:
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
    header_lines = str(header, 'latin-1').splitlines()
    return (
      header_lines[0],
      dict(l.split(': ', 1) for l in header_lines[1:]),
      t1-t0, t2-t1, body)

  @classmethod
  def get_kite_addrinfo(cls, kite):
    try:
      return socket.getaddrinfo(kite.name, cls.FE_PORT, socket.AF_INET, socket.SOCK_STREAM)
    except IOError:
      return []

  @classmethod
  def get_relays_addrinfo(cls):
    try:
      if cls.FE_NAME:
        return socket.getaddrinfo(cls.FE_NAME, cls.FE_PORT, socket.AF_INET, socket.SOCK_STREAM)
    except IOError:
      pass
    return []

  @classmethod
  def ping_relay(cls, relay_addr, bias=1.0):
    try:
      l1, hdrs, t1, t2, body = cls.http_get(
        'http', 'ping.pagekite', '/ping', relay_addr,
        atonce=250)

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
  def send_raw(cls, conn, data):
    data = bytes(data, 'latin-1')
    if cls.trace:
      cls.trace('>> %s' % data)
    conn.write(data)

  @classmethod
  def send_chunk(cls, conn, data):
    cls.send_raw(conn, '%x\r\n%s' % (len(data), data))

  @classmethod
  def send_data(cls, conn, frame, data):
    cls.send_chunk(conn, 'SID: %s\r\n\r\n%s' % (frame.sid, data))

  @classmethod
  def send_eof(cls, conn, frame):
    cls.send_chunk(conn, 'SID: %s\r\nEOF: 1WR\r\n\r\n' % (frame.sid,))

  @classmethod
  def send_pong(cls, conn, pong):
    cls.send_chunk(conn, 'NOOP: 1\r\nPONG: %s\r\n\r\n!' % (pong,))

  @classmethod
  def read_http_header(cls, conn):
    header = bytes()
    read_bytes = 1
    while header[-4:] != b'\r\n\r\n':
      byte = conn.read(1)
      if byte in (b'', None):
        raise EofTunnelError()
      header += byte
    if cls.trace:
      cls.trace('<< %s' % header)
    return header

  @classmethod
  def read_chunk(cls, conn):
    hdr = b''
    try:
      while not hdr.endswith(b'\r\n'):
        byte = conn.read(1)
        if byte in (b'', None):
          raise EofTunnelError()
        hdr += byte
      chunk_len = int(str(hdr, 'latin-1').strip(), 16)
      payload = conn.read(chunk_len)
      # FIXME: We might need a loop here, in case of short reads.
      #        And for self preservation, a possibly discard mode if the
      #        frame is too big for us to handle.
      if cls.trace:
        cls.trace('<< %s%s' % (hdr, payload))
      return payload
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
  def connect(cls, relay_addr, kites, global_secret):
    if cls.debug:
      cls.debug('Flying %s via %s' % (
        ', '.join(str(k) for k in kites), relay_addr))

    for kite in kites:
      kite.challenge = ''

    # Connect, get fresh challenges
    cfd, conn = sock_connect_stream(cls, relay_addr, ssl_wrap=cls.WITH_SSL)
    cls.send_raw(conn, (
        'CONNECT PageKite:1 HTTP/1.0\r\n'
        'X-PageKite-Features: AddKites\r\n'
        'X-PageKite-Version: %s\r\n'
        '%s\r\n'
      ) % (
        cls.APPVER,
        cls.x_pagekite(relay_addr, kites, global_secret)))

    # Make sense of it...
    challenge = cls.read_http_header(conn)
    ok, needsign, rejected = cls.parse_challenge(challenge, kites)
    if rejected:
      conn.close()
      raise RejectedError(', '.join(rejected))

    if needsign:
      cls.send_chunk(conn, (
          'NOOP: 1\r\n'
          '%s\r\n'
        ) % (
          cls.x_pagekite(relay_addr, needsign, global_secret)))
      challenge = cls.read_chunk(conn)
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
    return cfd, conn

  @classmethod
  def update_dns(cls, relay_ip, kites):
    proto, host, path_fmt = cls.DDNS_URL
    errors = 0
    for kite in kites:
      try:
        payload = '%s:%s' % (kite.name, relay_ip)
        l1, hdrs, t1, t2, body = cls.http_get(
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
        cls.debug('DNS update %s to %s: %s' % (
          kite.name, relay_ip, str(body, 'latin-1').strip()))

    return (errors == 0)
