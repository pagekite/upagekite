# Copyright (C) 2020-2022, The Beanstalks Project ehf. and Bjarni R. Einarsson.
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option)
# any later version.
#
# Commercial licenses are for sale. See the files README.md and COPYING.txt
# for more details.

import struct
from hashlib import sha1

from .proto import PermissionError, EofStream, asyncio, fuzzy_sleep_ms

try:
  from ubinascii import b2a_base64
  def sha1b64(data):
    return str(
      b2a_base64(sha1(bytes(data, 'latin-1')).digest()),
      'latin-1').strip()
except (NameError, ImportError):
  from base64 import b64encode
  def sha1b64(data):
    return str(
      b64encode(sha1(bytes(data, 'latin-1')).digest()),
      'latin-1').strip()


_WEBSOCKETS = {}


# Decorator for creating a websocket and registering the handler for
# incoming messages.
def websocket(ws_id=None, strict_origin=True, auth_check=None):
  def decorate(message_handler):
    async def url_handler(req_env):
      uPK = req_env['httpd'].uPK
      if auth_check is not None:
          try:
              auth_check(req_env)
          except PermissionError:
              return {'code': 403, 'msg': 'Access Denied'}

      hdrs = req_env['http_headers']
      if ((hdrs.get('Upgrade', '').lower() != 'websocket')
          or (not hdrs.get('Sec-WebSocket-Key'))
          or (hdrs.get('Sec-WebSocket-Protocol'))  # Unsupported!
          or (hdrs.get('Sec-WebSocket-Version', '13') not in ('13', ))):
        rv = None
        if 'Upgrade' not in hdrs:
          rv = await message_handler(None, None, None, None, websocket=False)
        elif uPK.debug:
          uPK.debug('Invalid Websocket request: %s' % (hdrs,))
        return rv or {'code': 400, 'msg': 'Invalid Request'}

      if strict_origin and (not hdrs.get('Host')
          or (('://'+hdrs.get('Host', '')) not in hdrs.get('Origin', ''))):
        return {'code': 403, 'msg': 'Forbidden'}

      live_conns = sum([len(ws.streams) for ws in _WEBSOCKETS.values()])
      if live_conns >= uPK.WEBSOCKET_MAX_CONNS:
        return {'code': 503, 'msg': 'Too Many Clients'}

      conn = req_env['conn']
      frame = req_env['frame']

      ws = Websocket.get(ws_id or req_env.frame.uid, message_handler, uPK)
      await ws.subscribe(conn, frame, req_env)

      key = req_env['http_headers']['Sec-WebSocket-Key']
      signature = sha1b64(key + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11')
      return {
        'code': 101,
        'msg': 'Switching Protocols',
        'mimetype': None,
        'hdrs': {
          'Upgrade': 'websocket',
          'Sec-WebSocket-Accept': signature,
          'Connection': 'Upgrade'},
        'eof': False}
    return url_handler
  return decorate


async def ws_broadcast(ws_ids, message, only=None):
  for _id in (ws_ids if isinstance(ws_ids, list) else [ws_ids]):
    try:
      await Websocket.get(_id).broadcast(message, only=only)
    except KeyError:
      pass


class OPCODES(object):
  CONT = 0x0
  TEXT = 0x1
  BINARY = 0x2
  CLOSE = 0x8
  PING = 0x9
  PONG = 0xa


class Websocket(object):
  def __init__(self, ws_id, message_handler, uPK):
    self.uPK = uPK
    self.ws_id = ws_id
    self.message_handler = message_handler
    self.streams = {}
    self.make_mask = uPK.WEBSOCKET_MASK

  @classmethod
  def get(cls, ws_id, message_handler=None, uPK=None):
    global _WEBSOCKETS
    if ws_id not in _WEBSOCKETS:
      if message_handler and uPK:
        _WEBSOCKETS[ws_id] = cls(ws_id, message_handler, uPK)
    return _WEBSOCKETS[ws_id]

  async def subscribe(self, conn, frame, env):
    if self.uPK.info:
      self.uPK.info('[ws/%s] Subscribe %s %s'
        % (self.ws_id, frame.uid, frame.remote_ip))

    wss = WebsocketStream(conn, frame, env, self.uPK, self.make_mask())
    self.streams[frame.uid] = wss
    conn.async_await_data(self.uPK, frame.sid, self.receive_data)

    async def welcome():
      await fuzzy_sleep_ms(25)
      await self.message_handler(None, None, wss, self, first=True)
    asyncio.get_event_loop().create_task(welcome())

  def unsubscribe(self, uid):
    # FIXME: Stop awaiting data
    if uid in self.streams:
      wss = self.streams[uid]
      if self.uPK.info:
        ip = wss.frame.remote_ip
        self.uPK.info('[ws/%s] Unsubscribe %s %s' % (self.ws_id, uid, ip))
      wss.conn.close(wss.frame.sid)
      del self.streams[uid]

  async def receive_data(self, frame):
    if frame.headers.get('NOOP'):
      return

    wss = self.streams.get(frame.uid)
    if not wss:
      return  # FIXME: Send back an EOF

    if frame.eof:
      self.unsubscribe(frame.uid)
      await self.message_handler(None, None, wss, self, eof=True)
    else:
      try:
        for opcode, message in wss.process(frame.payload):
          if opcode == OPCODES.TEXT:
            message = str(message, 'utf-8')
          if self.uPK.trace:
            self.uPK.trace('[ws/%s] Received %s %d/%s'
              % (self.ws_id, frame.uid, opcode or 0, message))
          if opcode == OPCODES.PING:
            await wss.send(message, OPCODES.PONG)
          else:
            await self.message_handler(opcode, message, wss, self)
      except EofStream:
        await self.message_handler(None, None, wss, self, eof=True)

  async def broadcast(self, msg, opcode=OPCODES.TEXT, only=None):
    msg = bytes(msg, 'utf-8') if (isinstance(msg, str)) else msg
    dead = []
    for k in self.streams:
      wss = self.streams[k]
      if (only is None) or only(wss):
        try:
          await wss.send(msg, opcode)
        except (KeyError, OSError, AttributeError):
          dead.append(k)
    for k in dead:
      del self.streams[k]


class WebsocketStream(object):
  HEADER_FIN = (1 << 7)
  HEADER_OPC = 0xf

  MASKING_BIT = (1 << 7)
  LENGTH_MASK = 0xff - MASKING_BIT

  LENGTH_7 = 0x7e
  LENGTH_16 = 1 << 16

  ZERO_MASK = b'\0\0\0\0'

  def __init__(self, conn, frame, env, uPK, mask=ZERO_MASK):
    self.uPK = uPK
    self.conn = conn
    self.frame = frame
    self.env = env
    self.mask = mask
    self.buffer = b''

  # Convenience properties
  uid = property(lambda s: s.frame.uid)
  remote_ip = property(lambda s: s.frame.remote_ip)

  def _apply_mask(self, mask, data):
    if mask == self.ZERO_MASK:
      return data
    for i in range(len(data)):
      data[i] ^= mask[i % 4]
    return data

  async def send(self, msg, opcode=OPCODES.TEXT):
    msg = bytes(msg, 'utf-8') if (isinstance(msg, str)) else msg

    masking = self.MASKING_BIT if (self.mask != self.ZERO_MASK) else 0

    buf = bytearray(b'01')
    buf[0] = (self.HEADER_FIN | opcode)
    buf[1] = masking

    length = len(msg)
    if length < self.LENGTH_7:
      buf[1] |= length
    elif length < self.LENGTH_16:
      buf[1] |= 0x7e
      buf += struct.pack('!H', length)
    else:
      buf[1] |= 0x7f
      buf += struct.pack('!Q', length)

    if masking:
      buf += self.mask
      buf += self._apply_mask(self.mask, bytearray(msg))
    else:
      buf += msg

    buf = bytes(buf)

    if self.uPK.trace:
      self.uPK.trace('[ws] Send %s opcode=%d len=%d: %s'
        % (self.frame.uid, opcode, len(buf), buf[:128]))

    await self.conn.reply(self.frame, buf, eof=False)

  def process(self, data):
    self.buffer += data
    try:
      opcode, message, offset = None, b'', 0
      while True:
        fin, opc, data, offset = self.extract_frame(offset)
        if opc in (OPCODES.TEXT, OPCODES.BINARY, OPCODES.CONT, OPCODES.PING):
          if opc != OPCODES.CONT:
            opcode = opc
          message += data
          if fin:
            yield (opcode, message)
            self.buffer = self.buffer[offset:]
            opcode, message, offset = None, b'', 0
        elif opc == OPCODES.CLOSE:
          raise EofStream()
        else:
          print('FIXME: handle control frame %s' % opc)
    except (KeyError, IndexError):
      pass

  def extract_frame(self, base):
    b0 = self.buffer[base]
    b1 = self.buffer[base+1]
    masking = (b1 & self.MASKING_BIT)
    length = (b1 & self.LENGTH_MASK)

    offset = 2
    if length == 0x7e:
      length = struct.unpack('!H', self.buffer[base+2:base+4])[0]
      offset = 4
    elif length == 0x7f:
      length = struct.unpack('!Q', self.buffer[base+2:base+10])[0]
      offset = 10

    if masking:
      mask = self.buffer[base+offset:base+offset+4]
      offset += 4
    else:
      mask = self.ZERO_MASK

    end = base+offset+length
    result = (
      (b0 & self.HEADER_FIN),
      (b0 & self.HEADER_OPC),
      self._apply_mask(mask, bytearray(self.buffer[base+offset:end])),
      end)

    return result
