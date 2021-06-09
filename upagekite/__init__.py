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

from .proto import asyncio, socket, ticks_ms, fuzzy_sleep_ms, Kite, Frame, EofTunnelError, uPageKiteDefaults


try:
  from ntptime import settime
except ImportError:
  settime = None

def _ntp_settime(uPK):
  if settime is not None:
    try:
      if uPK.info:
        uPK.info('Attempting to set the time using NTP...')
      settime()
    except Exception as e:
      if uPK.error:
        uPK.error('Failed to set NTP time: %s' % e)


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

  def sync_reply(self, frame, data=None, eof=True):
    if data:
      self.sock.setblocking(True)
      self.client.write(bytes(data, 'latin-1'))
    if eof:
      self.client.close()
      self.client = None

  async def reply(self, frame, data=None, eof=True):
    await fuzzy_sleep_ms()
    if data:
      self.sock.setblocking(True)
      self.client.write(bytes(data, 'latin-1'))
      await fuzzy_sleep_ms(int(len(data) * frame.uPK.MS_DELAY_PER_BYTE))
    if eof:
      self.client.close()
      self.client = None

  def await_data(self, uPK, sid, handler, nbytes):
    self.sock.setblocking(False)
    while nbytes > 0:
      more = self.client.read(min(2048, nbytes))
      handler(Frame(uPK, payload=more))
      if more:
        nbytes -= len(more)
      else:
        break

  def close(self):
    if self.client is not None:
      self.client.close()
    elif self.sock is not None:
      self.sock.close()
    self.sock = self.client = None

  async def process_io(self, uPK):
    self.sock = None
    try:
      self.sock, addr = self.fd.accept()
      if hasattr(self.sock, 'makefile'):
        self.client = self.sock.makefile('rwb')
      else:
        self.sock = self.client

      if uPK.trace:
        uPK.trace('Reading request from: %s' % (addr,))
      self.sock.setblocking(False)
      req = b''
      deadline = ticks_ms() + 500  # When to give up on data
      sleep_t = 20
      while (ticks_ms() < deadline) and (b'\r\n\r\n' not in req):
        await fuzzy_sleep_ms(min(sleep_t, 50))
        sleep_t += 5
        try:
          data = self.client.read(2048)
          if data is not None:
            req += data
        except socket.error:
          pass

      if uPK.trace:
        uPK.trace('Got local request: %s' % (req,))
      if b'\r\n\r\n' in req:
        await self.handler(self, self, Frame(uPK, payload=req, headers={
          'Host': '0.0.0.0',
          'Proto': 'http',
          'Port': self.listening_port,
          'RIP': '::ffff:%s' % (addr[0],)}))
      else:
        self.client.write(b'HTTP/1.0 408 Timed out\r\n\r\n')

    except KeyboardInterrupt:
      raise
    except Exception as e:
      print('Oops, process_io: %s' % e)
      return False
    finally:
      self.close()

    return True


class uPageKiteConn:
  def __init__(self, pk):
    self.pk = pk

  async def connect(self, relay_addr):
    pk = self.pk
    self.ip = pk.uPK.addr_to_quad(relay_addr)
    self.fd, self.conn = await pk.uPK.connect(relay_addr, pk.kites, pk.secret)
    now = int(time.time())
    self.last_data_ts = now
    self.last_settime = now
    self.handlers = {}
    return self

  def __str__(self):
    return "<uPageKiteConn(%s)>" % self.ip

  def sync_reply(self, frame, data=None, eof=True):
    uPK = self.pk.uPK
    if data:
      uPK.sync_send(self.conn, uPK.fmt_data(frame, data))
    if eof:
      uPK.sync_send(self.conn, uPK.fmt_eof(frame))

  async def reply(self, frame, data=None, eof=True):
    uPK = self.pk.uPK
    if data:
      await uPK.send(self.conn, uPK.fmt_data(frame, data))
    if eof:
      await uPK.send(self.conn, uPK.fmt_eof(frame))

  async def send_ping(self):
    await self.pk.uPK.send(self.conn, self.pk.uPK.fmt_ping())

  def await_data(self, uPK, sid, handler, nbytes):
    self.handlers[sid] = handler

  def close(self):
    self.handlers = {}
    if self.fd is not None:
      self.fd.close()
      self.fd = None

  async def process_io(self, uPK):
    try:
      frame = await self.pk.uPK.read_chunk(self.conn)
      self.last_data_ts = int(time.time())
      if frame:
        frame = Frame(uPK, frame)

        if frame.ping:
          # Should never happen, as we send our own pings much more frequently
          await self.pk.uPK.send(self.conn, self.pk.uPK.fmt_pong(frame.ping))

        elif frame.sid and frame.sid in self.handlers:
          try:
            await self.handlers[frame.sid](frame)
          except Exception as e:
            print('Oops, sid handler: %s' % e)
            await self.reply(frame, eof=True)
            if frame.sid in self.handlers:
              del self.handlers[frame.sid]

        elif frame.sid and frame.host and frame.proto:
          for kite in self.pk.kites:
            if kite.name == frame.host and kite.proto == frame.proto:
              # FIXME: We should allow the handler to return a callback
              #        for any subsequent data with the same SID, to
              #        allow for uploads or bidirectional comms.
              await kite.handler(kite, self, frame)
              break

        elif frame.sid:
          await self.reply(frame, eof=True)

        # FIXME: Detect and report quota values? Other things?

      # Zero-length chunks aren't an error condition
      return True
    except EofTunnelError:
      if self.pk.uPK.debug:
        self.pk.uPK.debug('EOF tunnel')
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

  async def async_poll(self, timeout_ms):
    deadline = ticks_ms() + timeout_ms
    while ticks_ms() < deadline:
      events = self.poll.poll(1)
      if events:
        if self.pk.uPK.trace:
          self.pk.uPK.trace('poll() returned: %s' % (events,))
        return events
      await fuzzy_sleep_ms(min(75, deadline - ticks_ms()))
    return []

  async def process_io(self, uPK, timeout_ms):
    count = 0
    if self.pk.uPK.trace:
      self.pk.uPK.trace('Entering poll(%d)' % timeout_ms)

    for (obj, event) in await self.async_poll(timeout_ms):
      if (event & select.POLLIN) or (event & select.POLLPRI):
        conn = self.conns[obj if (type(obj) == int) else obj.fileno()]
        if self.pk.uPK.trace:
          self.pk.uPK.trace('process_io(%s)' % conn)
        if await conn.process_io(uPK):
          count += 1
        else:
          self.pk.uPK.debug('conn.process_io() returned False')
          return False
      elif event & select.POLLOUT:
        pass
      else:
        return False

    if count == 0:
      dead = int(time.time()) - max(
        self.pk.uPK.MIN_CHECK_INTERVAL * 6,
        self.pk.uPK.TUNNEL_TIMEOUT)
      for conn in self.conns.values():
        if hasattr(conn, 'send_ping'):
          if conn.last_data_ts < dead:
            if self.pk.uPK.info:
              self.pk.uPK.info(
                'No PING response from %s, assuming it is down.' % (conn,))
            return False
          elif conn.last_data_ts < dead + (self.pk.uPK.MIN_CHECK_INTERVAL * 2):
            await conn.send_ping()

    return count


class uPageKite:
  def __init__(self, kites, socks=[], uPK=uPageKiteDefaults, public=True):
    self.uPK = uPK
    self.keep_running = True
    self.public = public
    self.kites = kites
    self.socks = socks
    self.secret = uPK.make_random_secret([(k.name, k.secret) for k in kites])
    self.want_dns_update = [0]
    self.reconfig_flag = False

  def reconfigure(self):
    self.reconfig_flag = True
    return self

  async def choose_relays(self, preferred=[]):
    await fuzzy_sleep_ms()

    relays = []
    if len(self.kites) == 0:
      return relays

    await self.uPK.check_fe_hint_url()

    for kite in self.kites:
      for a in await self.uPK.get_kite_addrinfo(kite):
        if a[-1] not in relays and len(relays) < 10:
          relays.append(a[-1])

    if self.kites:
      for a in await self.uPK.get_relays_addrinfo():
        if a[-1] not in relays and len(relays) < 10:
          relays.append(a[-1])
    if not relays:
      if self.kites and self.uPK.info:
        self.uPK.info('No relays found in DNS, is our Internet down?')
      return []

    if len(relays) == 1:
      return relays

    pings = [0] * len(relays)
    for i, relay_addr in enumerate(relays):
      bias = 0.9 if (not i or relay_addr in preferred) else 1.0
      pings[i] = await self.uPK.ping_relay(relay_addr, bias)

    relays = list(zip(pings, relays))
    fastest = min(relays)
    if fastest != relays[0]:
      return [fastest[-1], relays[0][-1]]
    else:
      return [relays[0][-1]]

  async def connect_relays(self, relays, now):
    conns = []
    self.want_dns_update = [0]
    for relay in relays:
      await fuzzy_sleep_ms()
      try:
        conns.append(await uPageKiteConn(self).connect(relay))
      except KeyboardInterrupt:
        raise
      except Exception as e:
        if self.uPK.error:
          self.uPK.error('Failed to connect %s: %s' % (relay, e))
    if conns:
      self.want_dns_update = [now - 1, conns[0].ip]
    return conns

  async def relay_loop(self, conns, deadline):
    max_timeout = 5005
    wdt = None
    try:
      if self.uPK.WATCHDOG_TIMEOUT:
        from machine import WDT
        wdt = WDT(timeout=self.uPK.WATCHDOG_TIMEOUT)
        max_timeout = min(max_timeout, self.uPK.WATCHDOG_TIMEOUT // 2)
    except KeyboardInterrupt:
      raise
    except:
      pass

    await fuzzy_sleep_ms()
    try:
      pool = uPageKiteConnPool(conns, self)
      while pool.conns and time.time() < deadline:
        if wdt:
          wdt.feed()

        self.uPK.GC_COLLECT()
        timeout_ms = min(max(100, (deadline - time.time()) * 1000), max_timeout)
        await fuzzy_sleep_ms()
        if await pool.process_io(self.uPK, int(timeout_ms)) is False:
          raise EofTunnelError('process_io returned False')

        if self.reconfig_flag:
          if self.uPK.info:
            self.uPK.info("Exiting relay_loop early: reconfiguration requested.")
          return False

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
  async def tick(self, **attrs):
    if self.uPK.info:
      self.uPK.info("Tick: %s %s%s"
        % (self.uPK.APPNAME, self.uPK.APPVER,
           ''.join('; %s=%s' % pair for pair in attrs.items())))

  async def check_relays(self, now, back_off):
    self.want_dns_update = [0]
    relays = await self.choose_relays()
    if relays:
      relays = await self.connect_relays(relays, now)
      # FIXME: Did we fail to make some connections?

    if relays:
      back_off = 1
    else:
      back_off = min(back_off * 2,
        self.uPK.MAX_CHECK_INTERVAL // self.uPK.MIN_CHECK_INTERVAL)
      if self.uPK.info:
        self.uPK.info(
          "Next connection attempt in %d+ seconds..."
          % (back_off * self.uPK.MIN_CHECK_INTERVAL))

    return relays, back_off

  async def check_dns(self, now, relays, back_off):
    recheck_max = 0
    if now > 3600:
      recheck_max = max(0, 3600 // self.uPK.MIN_CHECK_INTERVAL)
      if 1 < self.want_dns_update[0] <= recheck_max:
        self.want_dns_update[0] -= 1
    else:
      pass  # Clock is wonky, disable the recheck magic for now

    if 1 == self.want_dns_update[0]:
      self.want_dns_update[0] = recheck_max
      for kite in self.kites:
        if self.uPK.trace:
          self.uPK.trace("Checking current DNS state for %s" % kite)
        for a in self.uPK.get_kite_addrinfo(kite):
          if a and a[-1] and (a[-1][0] not in self.want_dns_update):
            if self.uPK.info:
              self.uPK.info(
                "DNS for %s is wrong (%s), will update" % (kite, a[-1][0]))
            self.want_dns_update[0] = now + (back_off * self.uPK.MIN_CHECK_INTERVAL * 2)
            # FIXME: Was that the right thing to do?

    if recheck_max < self.want_dns_update[0] < now:
      if await self.uPK.update_dns(self.want_dns_update[1], self.kites):
        self.want_dns_update[0] = recheck_max
        if relays:
          back_off = 1
      else:
        back_off = min(back_off * 2,
          self.uPK.MAX_CHECK_INTERVAL // self.uPK.MAX_CHECK_INTERVAL)
        self.want_dns_update[0] = now + (back_off * self.uPK.MIN_CHECK_INTERVAL * 2)
        if self.uPK.info:
          self.uPK.info(
            "Next DNS update attempt in %d+ seconds..."
            % (self.want_dns_update[0] - now))

    return relays, back_off

  async def main(self):
    if time.time() < 0x27640000:
      _ntp_settime(self.uPK)

    next_check = int(time.time())
    back_off = 1
    relays = []
    while self.keep_running:
      self.reconfig_flag = False
      now = int(time.time())
      await self.tick(
        back_off=back_off,
        relays=len(relays),
        socks=len(self.socks),
        mem_free=(gc.mem_free() if hasattr(gc, 'mem_free') else 'unknown'))

      await fuzzy_sleep_ms()
      if next_check <= now:
        self.uPK.GC_COLLECT()

        # Check our relay status? Reconnect?
        if self.public and not relays:
          relays, back_off = await self.check_relays(now, back_off)
          await fuzzy_sleep_ms()

        # Is DNS up to date?
        if self.public and relays:
          relays, back_off = await self.check_dns(now, relays, back_off)
          await fuzzy_sleep_ms()

      # Schedule our next check; it should be neither too far in the future,
      # nor in the distant past. Clocks can misbehave, so we check for both.
      if next_check > now + back_off * self.uPK.MIN_CHECK_INTERVAL:
        next_check = now + back_off * self.uPK.MIN_CHECK_INTERVAL
      while next_check <= now:
        next_check += back_off * self.uPK.MIN_CHECK_INTERVAL

      # Process IO events for a while, or sleep.
      if relays or self.socks:
        if not await self.relay_loop(relays, now + self.uPK.TICK_INTERVAL):
          if relays:
            # We had a working connection, it broke! Reconnect ASAP.
            next_check = now
            for conn in relays:
              conn.close()
            relays = []
      else:
        if self.uPK.debug:
          self.uPK.debug("No sockets available, sleeping until %x" % next_check)
        await fuzzy_sleep_ms(999 * max(0, next_check - int(time.time())))

  def run(self):
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(self.main())
    finally:
        loop.close()
