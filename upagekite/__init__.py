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

from .proto import Kite, Frame, EofTunnelError, uPageKiteDefaults


class uPageKiteConn:
  def __init__(self, relay_addr, pk):
    self.pk = pk
    self.fd, self.conn = pk.proto.connect(relay_addr, pk.kites, pk.secret)
    self.pk.last_data_ts = time.time()

  def reply(self, frame, data=None, eof=True):
    if data:
      self.pk.proto.send_data(self.conn, frame, data)
    if eof:
      self.pk.proto.send_eof(self.conn, frame)

  def process_chunk(self):
    try:
      frame = self.pk.proto.read_chunk(self.conn)
      self.pk.last_data_ts = time.time()
      if frame:
        frame = Frame(frame)

        if frame.ping:
          self.pk.proto.send_pong(self.conn, frame.ping)

        elif frame.sid and frame.host and frame.proto:
          for kite in self.pk.kites:
            if kite.name == frame.host and kite.proto == frame.proto:
              # FIXME: We should allow the handler to return a callback
              #        for any subsequent data with the same SID, to
              #        allow for uploads or bidirectional comms.
              kite.handler(kite, self, frame)
              break

        # FIXME: Detect additional data for an established stream
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
    self.poll = select.poll()
    for fno in self.conns:
      self.poll.register(self.conns[fno].fd, select.POLLIN)

  def process_chunks(self, timeout=2000):
    count = 0
    for (obj, event) in self.poll.poll(timeout):
      if event != select.POLLIN:
        return False
      conn = self.conns[obj if (type(obj) == int) else obj.fileno()]
      if conn.process_chunk():
        count += 1
      else:
        return False
    return count


class uPageKite:
  def __init__(self, kites, proto=uPageKiteDefaults):
    self.proto = proto
    self.keep_running = True
    self.last_data_ts = 0
    self.kites = kites
    self.secret = proto.make_random_secret([(k.name, k.secret) for k in kites])

  def choose_relays(self, preferred=[]):
    relays = []
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

  def relay_loop(self, relays):
    gc.collect()
    processed = 0
    conns = []
    try:
      for relay in relays:
        try:
          conns.append(uPageKiteConn(relay, self))
        except Exception as e:
          if self.proto.error:
            self.proto.error('Failed to connect %s: %s' % (relay, e))

      if conns:
        # FIXME: Update dynamic DNS with the details for our preferred
        #        relay (which should be relays[0]).
        pool = uPageKiteConnPool(conns, self)
        while True:
          count = pool.process_chunks()
          if count is False:
            break
          elif count:
            processed += count
          else:
            pass  # We are idle, do housekeeping?

      return processed
    finally:
      for conn in conns:
        try:
          conn.close()
        except:
          pass

  def run(self):
    fallback = 1
    while self.keep_running:
      relays = self.choose_relays()
      if relays and self.relay_loop(relays) > 0:
        fallback = 1

      if fallback > 1:
        if self.proto.info:
          self.proto.info("Sleeping %d seconds..." % fallback)
        time.sleep(fallback)
      fallback = min(fallback * 2, 64)
