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
import gc
import time
import select

from .proto import socket, Kite, Frame, EofTunnelError, uPageKiteDefaults


try:
  from ntptime import settime
except ImportError:
  settime = None

def _ntp_settime(proto):
  if settime is not None:
    try:
      if proto.info:
        proto.info('Attempting to set the time using NTP...')
      settime()
    except:
      if proto.error:
        proto.error('Failed to set NTP time: %s' % e)


class LocalHTTPKite(Kite):
  def __init__(self, listen_on, name, secret, handler):
    Kite.__init__(self, name, secret, 'http', handler)
    self.listening_port = listen_on
    self.handlers = {}
    try:
      self.fd = socket.socket()
      self.fd.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
      self.fd.bind(socket.getaddrinfo('0.0.0.0', listen_on)[0][-1])
      self.fd.listen(5)
    except Exception as e:
      print("Oops, binding socket failed: %s" % e)
      self.fd = None
    self.client = None
    self.sock = None

  def __str__(self):
    return '<LocalHTTPKite(%s://%s):%d>' % (
      self.proto, self.name, self.listening_port)

  def reply(self, frame, data=None, eof=True):
    if data:
      self.sock.setblocking(True)
      self.client.write(bytes(data, 'latin-1'))
    if eof:
      self.client.close()
      self.client = None

  def await_data(self, sid, handler, nbytes):
    self.sock.setblocking(True)
    while nbytes > 0:
      more = self.client.read(min(2048, nbytes))
      handler(Frame(payload=more))
      if more:
        nbytes -= len(more)
      else:
        break

  def close(self):
    if self.sock:
      self.sock.close()

  def process_io(self):
    self.sock = None
    try:
      self.sock, addr = self.fd.accept()
      if hasattr(self.sock, 'makefile'):
        self.client = self.sock.makefile('rwb')
      else:
        self.sock = self.client

      req = self.client.read(1)
      self.sock.setblocking(False)
      req += self.client.read(4095)

      self.handler(self, self, Frame(payload=req, headers={
        'Host': '0.0.0.0',
        'Proto': 'http',
        'Port': self.listening_port,
        'RIP': '::ffff:%s' % (addr[0],)}))

    except KeyboardInterrupt:
      raise
    except Exception as e:
      print('Oops, process_io: %s' % e)
      return False
    finally:
      self.close()

    return True


class uPageKiteConn:
  def __init__(self, relay_addr, pk):
    self.pk = pk
    self.ip = pk.proto.addr_to_quad(relay_addr)
    self.fd, self.conn = pk.proto.connect(relay_addr, pk.kites, pk.secret)
    now = int(time.time())
    self.last_data_ts = now
    self.last_settime = now
    self.handlers = {}

  def __str__(self):
    return "<uPageKiteConn(%s)>" % self.ip

  def reply(self, frame, data=None, eof=True):
    if data:
      self.pk.proto.send_data(self.conn, frame, data)
    if eof:
      self.pk.proto.send_eof(self.conn, frame)

  def send_ping(self):
    self.pk.proto.send_ping(self.conn)

  def await_data(self, sid, handler, nbytes):
    self.handlers[sid] = handler

  def close(self):
    self.handlers = {}
    self.fd.close()

  def process_io(self):
    try:
      frame = self.pk.proto.read_chunk(self.conn)
      self.last_data_ts = int(time.time())
      if frame:
        frame = Frame(frame)

        if frame.ping:
          # Should never happen, as we send our own pings much more frequently
          self.pk.proto.send_pong(self.conn, frame.ping)

        elif frame.sid and frame.sid in self.handlers:
          try:
            self.handlers[frame.sid](frame)
          except Exception as e:
            print('Oops, sid handler: %s' % e)
            self.reply(frame, eof=True)
            if frame.sid in self.handlers:
              del self.handlers[frame.sid]

        elif frame.sid and frame.host and frame.proto:
          for kite in self.pk.kites:
            if kite.name == frame.host and kite.proto == frame.proto:
              # FIXME: We should allow the handler to return a callback
              #        for any subsequent data with the same SID, to
              #        allow for uploads or bidirectional comms.
              kite.handler(kite, self, frame)
              break

        elif frame.sid:
          self.reply(frame, eof=True)

        # FIXME: Detect and report quota values? Other things?

      # Zero-length chunks aren't an error condition
      return True
    except EofTunnelError:
      if self.pk.proto.debug:
        self.pk.proto.debug('EOF tunnel')
      return False


class uPageKiteConnPool:
  def __init__(self, conns, pk):
    self.pk = pk

    self.conns = dict((c.fd.fileno(), c) for c in conns)
    for so in pk.socks:
      if so.fd:
        self.conns[so.fd.fileno()] = so

    self.poll = select.poll()
    for fno in self.conns:
      self.poll.register(self.conns[fno].fd, select.POLLIN)

  def process_io(self, timeout):
    count = 0
    if self.pk.proto.trace:
      self.pk.proto.trace('Entering poll(%d)' % timeout)
    for (obj, event) in self.poll.poll(timeout):
      if event != select.POLLIN:
        return False
      conn = self.conns[obj if (type(obj) == int) else obj.fileno()]
      if self.pk.proto.trace:
        self.pk.proto.trace('process_io(%s)' % conn)
      if conn.process_io():
        count += 1
      else:
        return False

    dead = int(time.time()) - max(
      self.pk.proto.MIN_CHECK_INTERVAL * 6,
      self.pk.proto.TUNNEL_TIMEOUT)
    for conn in self.conns.values():
      if hasattr(conn, 'send_ping'):
        if conn.last_data_ts < dead:
          if self.pk.proto.info:
            self.pk.proto.info(
              'No PING response from %s, assuming it is down.' % (conn,))
          return False
        elif conn.last_data_ts < dead + (self.pk.proto.MIN_CHECK_INTERVAL * 2):
          conn.send_ping()

    return count


class uPageKite:
  def __init__(self, kites, socks=[], proto=uPageKiteDefaults):
    self.proto = proto
    self.keep_running = True
    self.kites = kites
    self.socks = socks
    self.secret = proto.make_random_secret([(k.name, k.secret) for k in kites])
    self.want_dns_update = [0]

  def choose_relays(self, preferred=[]):
    gc.collect()
    relays = []
    if len(self.kites) == 0:
      return relays

    for kite in self.kites:
      for a in self.proto.get_kite_addrinfo(kite):
        if a[-1] not in relays and len(relays) < 10:
          relays.append(a[-1])
    for a in self.proto.get_relays_addrinfo():
      if a[-1] not in relays and len(relays) < 10:
        relays.append(a[-1])
    if not relays:
      if self.proto.info:
        self.proto.info('No relays found in DNS, is our Internet down?')
      return []

    if len(relays) == 1:
      return relays

    pings = [0] * len(relays)
    for i, relay_addr in enumerate(relays):
      bias = 0.9 if (not i or relay_addr in preferred) else 1.0
      pings[i] = self.proto.ping_relay(relay_addr, bias)

    relays = list(zip(pings, relays))
    fastest = min(relays)
    if fastest != relays[0]:
      return [fastest[-1], relays[0][-1]]
    else:
      return [relays[0][-1]]

  def connect_relays(self, relays, now):
    conns = []
    self.want_dns_update = [0]
    for relay in relays:
      try:
        conns.append(uPageKiteConn(relay, self))
      except KeyboardInterrupt:
        raise
      except Exception as e:
        if self.proto.error:
          self.proto.error('Failed to connect %s: %s' % (relay, e))
    if conns:
      self.want_dns_update = [now - 1, conns[0].ip]
    return conns

  def relay_loop(self, conns, deadline):
    max_timeout = 30000
    wdt = None
    try:
      if self.proto.WATCHDOG_TIMEOUT:
        from machine import WDT
        wdt = WDT(timeout=self.proto.WATCHDOG_TIMEOUT)
        max_timeout = min(max_timeout, self.proto.WATCHDOG_TIMEOUT // 2)
    except KeyboardInterrupt:
      raise
    except:
      pass

    gc.collect()
    try:
      pool = uPageKiteConnPool(conns, self)
      while pool.conns and time.time() < deadline:
        if wdt:
          wdt.feed()

        timeout = min(max_timeout, max(100, (deadline - time.time()) * 1000))
        gc.collect()
        if pool.process_io(int(timeout)) is False:
          raise EofTunnelError('process_io returned False')

      # Happy ending!
      return True
    except KeyboardInterrupt:
      raise
    except Exception as e:
      print('Oops, relay_loop: %s' % e)

    # We've fallen through to our unhappy ending, clean up
    for conn in conns:
      try:
        conn.close()
      except Exception as e:
        print("Oops, close(%s): %s" % (conn, e))
    return False

  # This is easily overridden by subclasses
  def tick(self, **attrs):
    if self.proto.info:
      self.proto.info("Tick: %s %s%s"
        % (self.proto.APPNAME, self.proto.APPVER,
           ''.join('; %s=%s' % pair for pair in attrs.items())))

  def check_relays(self, now, back_off):
    self.want_dns_update = [0]
    relays = self.choose_relays()
    if relays:
      relays = self.connect_relays(relays, now)
      # FIXME: Did we fail to make some connections?

    if relays:
      back_off = 1
    else:
      back_off = min(back_off * 2,
        self.proto.MAX_CHECK_INTERVAL // self.proto.MIN_CHECK_INTERVAL)
      if self.proto.info:
        self.proto.info(
          "Next connection attempt in %d+ seconds..."
          % (back_off * self.proto.MIN_CHECK_INTERVAL))

    return relays, back_off

  def check_dns(self, now, relays, back_off):
    recheck_max = 0
    if now > 3600:
      recheck_max = max(0, 3600 // self.proto.MIN_CHECK_INTERVAL)
      if 1 < self.want_dns_update[0] <= recheck_max:
        self.want_dns_update[0] -= 1
    else:
      pass  # Clock is wonky, disable the recheck magic for now

    if 1 == self.want_dns_update[0]:
      self.want_dns_update[0] = recheck_max
      for kite in self.kites:
        if self.proto.trace:
          self.proto.trace("Checking current DNS state for %s" % kite)
        for a in self.proto.get_kite_addrinfo(kite):
          if a[-1][0] not in self.want_dns_update:
            if self.proto.info:
              self.proto.info(
                "DNS for %s is wrong (%s), will update" % (kite, a[-1][0]))
            self.want_dns_update[0] = now + (back_off * self.proto.MIN_CHECK_INTERVAL * 2)
            # FIXME: Was that the right thing to do?

    if recheck_max < self.want_dns_update[0] < now:
      if self.proto.update_dns(self.want_dns_update[1], self.kites):
        self.want_dns_update[0] = recheck_max
        if relays:
          back_off = 1
      else:
        back_off = min(back_off * 2,
          self.proto.MAX_CHECK_INTERVAL // self.proto.MAX_CHECK_INTERVAL)
        self.want_dns_update[0] = now + (back_off * self.proto.MIN_CHECK_INTERVAL * 2)
        if self.proto.info:
          self.proto.info(
            "Next DNS update attempt in %d+ seconds..."
            % (self.want_dns_update[0] - now))

    return relays, back_off

  def run(self):
    if time.time() < 0x27640000:
      _ntp_settime(self.proto)

    next_check = int(time.time())
    back_off = 1
    relays = []
    while self.keep_running:
      now = int(time.time())
      self.tick(
        back_off=back_off,
        relays=len(relays),
        socks=len(self.socks),
        mem_free=(gc.mem_free() if hasattr(gc, 'mem_free') else 'unknown'))

      if next_check <= now:
        # Check our relay status? Reconnect?
        if not relays:
          relays, back_off = self.check_relays(now, back_off)

        # Is DNS up to date?
        if relays:
          relays, back_off = self.check_dns(now, relays, back_off)

      # Schedule our next check; it should be neither too far in the future,
      # nor in the distant past. Clocks can misbehave, so we check for both.
      if next_check > now + back_off * self.proto.MIN_CHECK_INTERVAL:
        next_check = now + back_off * self.proto.MIN_CHECK_INTERVAL
      while next_check <= now:
        next_check += back_off * self.proto.MIN_CHECK_INTERVAL

      # Process IO events for a while, or sleep.
      if relays or self.socks:
        if not self.relay_loop(relays, now + self.proto.TICK_INTERVAL):
          if relays:
            # We had a working connection, it broke! Reconnect ASAP.
            next_check = now
          relays = []
      else:
        if self.proto.debug:
          self.proto.debug("No sockets available, sleeping until %x" % next_check)
        time.sleep(max(0, next_check - int(time.time())))
