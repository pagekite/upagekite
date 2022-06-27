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
import os
import sys
import time
import json

from .proto import IOError, asyncio, print_exc, fuzzy_sleep_ms


class ProxyConn:
  def __init__(self, manager, conn, frame):
    self.manager = manager
    self.frame = frame
    self.conn = conn
    self.reader = None
    self.writer = None
    self.read_bytes = 0
    self.sent_bytes = 0

  async def process_reads(self):
    code = None
    while code is None:
      try:
        await fuzzy_sleep_ms()
        data = await self.reader.read(2048)
        if data:
          await self.conn.reply(self.frame, data, eof=False)
          self.sent_bytes += len(data)
        else:
          await self.conn.reply(self.frame, None, eof=True)
          code = 200
      except (IOError, OSError) as e:
        code = 500
    self.manager.log_request(self.frame, code,
      sent=self.sent_bytes,
      rcvd=self.read_bytes)

  async def connect(self, loop, host, port):
    try:
      pair = await asyncio.open_connection(host, port)
      self.reader, self.writer = pair
      if self.reader and self.writer:
        self.conn.async_await_data(self.manager.uPK, self.frame.sid, self.handle)
        await self.handle(self.frame)
        loop.create_task(self.process_reads())
        return self
    except (IOError, OSError) as e:
      print_exc(e)  # FIXME: spammy?
    try:
      if self.reader:
        self.reader.close()
      if self.writer:
        self.writer.close()
    except (IOError, OSError):
      print_exc(e)  # FIXME: spammy?
    return None

  async def handle(self, frame, first=False):
    eof = frame.eof
    eof_r = ('R' in eof)
    eof_w = ('W' in eof)
    if eof and (not eof_r) and (not eof_w):
      eof_w = eof_r = True

    if self.writer:
      if frame.payload:
        self.writer.write(frame.payload)
        self.read_bytes += len(frame.payload)
      try:
        await self.writer.drain()
      except (OSError, IOError) as e:
        pass
      if eof_w:
        self.writer.close()
        self.writer = None

    return eof_r


class ProxyManager:
  def __init__(self, name, dest_host, dest_port, uPK):
    self.uPK = uPK
    self.name = name
    self.dest_host = dest_host
    self.dest_port = int(dest_port)
    self.conns = {}

  def log_request(self, frame, code, sent='-', rcvd='-'):
    if self.uPK.info:
      self.uPK.info('[%s] - %s - - %s:%s - %s %s %s -' % (
        self.name, frame.remote_ip,
        frame.host, frame.port, code, sent, rcvd))

  async def _err(self, conn, frame, code, sent='-', rcvd='-'):
    self.log_request(frame, code, sent, rcvd)
    return await conn.reply(frame, None, eof=True)

  async def handle_proxy_frame(self, kite, conn, frame):
    self.uPK.GC_COLLECT()

    try:
      conn_id = '%s/%s' % (conn, frame.sid)
      pc = self.conns.get(conn_id)
      if pc is None:
        pc = await ProxyConn(self, conn, frame).connect(
          asyncio.get_event_loop(),
          self.dest_host, self.dest_port)
        if pc:
          self.conns[conn_id] = pc
        else:
          await self._err(conn, frame, 503)
      elif not await pc.handle(frame):
        print('CLOSING: %s' % frame.sid)
        pc.conn.close(sid=frame.sid)
        del self.conns[conn_id]

    except Exception as e:
      if self.uPK.debug:
        print_exc(e)
        self.uPK.debug('Exception in handle_proxy_frame: %s(%s)' % (type(e), e))
      return await self._err(conn, frame, 500)
