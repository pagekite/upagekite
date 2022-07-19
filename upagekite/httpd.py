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

from .proto import print_exc, asyncio, ilistdir, upk_open, fuzzy_sleep_ms
from .proto import PermissionError

try:
  from uos import stat
  def size(fn):
    return stat(fn)[6]
except ImportError:
  from os.path import getsize as size


_HANDLERS = {}

_MIMETYPES = {
  'css': 'text/css',
  'gif': 'image/gif',
  'htm': 'text/html; charset=utf-8',
  'html': 'text/html; charset=utf-8',
  'jpg': 'image/jpeg',
  'jpeg': 'image/jpeg',
  'js': 'text/javascript',
  'json': 'application/json',
  'md': 'text/plain; charset=utf-8',
  'pdf': 'application/pdf',
  'txt': 'text/plain; charset=utf-8',
  'xml': 'application/xml',
  '_default': 'application/octet-stream'}


# Method for registering new file-extension -> MIME type mappings
def register_mime_extensions(**kwargs):
  for k in kwargs:
    _MIMETYPES[str(k).lower()] = kwargs[k]


# Decorator for registering functions as URL handlers
def url(*paths, **attrs):
  def decorate(func):
    for path in paths:
      _HANDLERS[path] = (func, attrs)
    return func
  return decorate


# Decorator for registering async functions as URL handlers
def async_url(*paths, **attrs):
  attrs['_async'] = True
  return url(*paths, **attrs)


# Helper to look up a mimetype
def filename_to_mimetype(fn):
  return _MIMETYPES.get(fn.rsplit('.', 1)[-1].lower(), _MIMETYPES['_default'])


# Helper for iterating over chunks of a buffer
def buffer_byte_chunks(buf, chunksize):
  start, end = 0, min(len(buf), chunksize)
  while start < len(buf):
    data = buf[start:end]
    yield bytes(data, 'utf-8') if isinstance(data, str) else bytes(data)
    start, end = end, min(len(buf), end + chunksize)


# Helper to read file descriptor right up until the end
def _read_fd_iterator(fd, readsize, first_item=None):
  if first_item is not None:
    yield first_item
  while True:
    data = fd.read(readsize)
    if data:
      yield data
    else:
      break


def _items(obj):
  if hasattr(obj, 'items'):
    return obj.items()
  return obj


# Helper class for navigating the request environment
class ReqEnv:
  def __init__(self, env):
    self.env = env

  def __setitem__(self, *a, **kwa): return self.env.__setitem__(*a, **kwa)
  def __getitem__(self, *a, **kwa): return self.env.__getitem__(*a, **kwa)
  def __delitem__(self, *a, **kwa): return self.env.__delitem__(*a, **kwa)
  def __iter__(self, *a, **kwa): return self.env.__iter__(*a, **kwa)
  def update(self, *a, **kwa): return self.env.update(*a, **kwa)
  def values(self, *a, **kwa): return self.env.values(*a, **kwa)
  def items(self, *a, **kwa): return self.env.items(*a, **kwa)
  def keys(self, *a, **kwa): return self.env.keys(*a, **kwa)
  def get(self, *a, **kwa): return self.env.get(*a, **kwa)

  # Details about the client
  remote_ip = property(lambda s: s.env['frame'].remote_ip)
  is_local = property(lambda s: (
    s.remote_ip.startswith('127.') or
    s.remote_ip.startswith('::ffff:127.') or
    s.remote_ip == '::1'))

  # Details about the HTTP request
  post_data = property(lambda s: s['http_headers'].get('_post_data', {}))
  # Note: micropython needs _items() here
  post_vars = property(lambda s: dict(_items(s.post_data)))
  query_vars = property(lambda s: dict(_items(s['http_headers']['_qs'])))
  query_tuples = property(lambda s: s['http_headers']['_qs'])
  request_path = property(lambda s: s['http_headers']['_path'])
  http_method = property(lambda s: s['http_headers']['_method'])
  http_headers = property(lambda s: s['http_headers'])
  http_host = property(lambda s: s['frame'].host)
  http_port = property(lambda s: s['frame'].port)
  payload = property(lambda s: s['frame'].payload)
  frame = property(lambda s: s['frame'])


class HTTPD:
  METHODS = (
    'GET',
    'HEAD',
    'POST')

  def __init__(self, name, webroot, env, uPK):
    self.uPK = uPK
    self.name = name
    self.webroot = webroot
    self.static_max_age = 3600
    self.base_env = env

  @classmethod
  def unquote(cls, quoted):
    quoted = bytes(quoted, 'latin-1') if isinstance(quoted, str) else quoted
    _in = quoted.split(b'%')
    _out = [_in[0]]
    for frag in _in[1:]:
      try:
        _out.extend([bytes([int(frag[:2], 16)]), frag[2:]])
      except ValueError:
        _out.append(b'%', frag)
    joined = b''.join(_out)
    try:
      return str(joined, 'utf-8')
    except UnicodeError:
      try:
        return str(joined, 'latin-1')
      except UnicodeError:
        return quoted

  @classmethod
  def qs_to_list(cls, qs):
    if not qs:
      return []
    return [
      [cls.unquote(part) for part in pair.split('=', 1)]
      for pair in qs.split('&')]

  def http_response(self, code, msg, mimetype, ttl=None, hdrs={}):
    for hdr, default in (
            ('Access-Control-Allow-Origin', self.uPK.HTTP_CORS_ORIGIN),
            ('Access-Control-Allow-Methods', self.uPK.HTTP_CORS_METHODS),
            ('Access-Control-Allow-Headers', self.uPK.HTTP_CORS_HEADERS),
            ('Content-Security-Policy', self.uPK.HTTP_CONTENT_SECURITY_POLICY),
            ('Referrer-Policy', self.uPK.HTTP_REFERRER_POLICY)):
        if default:
            if hdr not in hdrs:
                hdrs[hdr] = default
    return (
        'HTTP/%s %d %s\r\n'
        'Server: %s\r\n'
        '%s%s%s\r\n'
      ) % (
        '1.1' if ('Upgrade' in hdrs) else '1.0',
        code, msg, self.uPK.APPURL,
        ('Content-Type: %s\r\n' % mimetype) if mimetype else '',
        ('Cache-Control: max-age=%d, private\r\n' % ttl) if ttl else '',
        ''.join('%s: %s\r\n' % (k, v) for k, v in hdrs.items()))

  def log_request(self, frame, method, path, code,
                  sent='-', headers={}, user='-'):
    if self.uPK.info:
      self.uPK.info('[www] %s %s - %s %s:%s%s - %s %s - %s' % (
        user, frame.remote_ip,
        method, frame.host, frame.port, path,
        code, sent,
        headers.get('User-Agent', headers.get('user-agent', '-'))))

  async def _err(self, code, msg, method, path, conn, frame, headers={}):
    self.log_request(frame, method, path, code, headers=headers)
    hdrs = {'WWW-Authenticate': 'Basic'} if (code == 401) else {}
    await conn.reply(frame,
      self.http_response(code, msg, 'text/plain', hdrs=hdrs)+msg+'\n')

  async def background_send(self,
        iterator, first_reply, conn, frame, method, path, hdrs, _close=[]):
    # Abort the upload if the remote end closes the connection
    saw_eof = [False]
    progress = [0]
    def beware_eof(frm):
      saw_eof[0] = saw_eof[0] or ('W' in frm.eof)
      if 'SKB' in frm.headers:
        progress[0] = int(frm.headers['SKB'])

    # Iteratively send our data
    async def async_send_data():
      sent = 0
      code = 200
      want_eof = True
      sent_first = False
      try:
        await fuzzy_sleep_ms(10)

        first_item = next(iterator)
        if method == 'HEAD':
          first_item['eof'] = True
          first_item['suppress_log'] = False
          first_reply(**first_item)
          want_eof = False
          sent_first = True
          return

        want_eof = first_item.get('eof', want_eof)
        first_item['eof'] = False
        sent = first_reply(**first_item)
        sent_first = True

        # Note: The order and type of sleeps here is important; if we do
        #       not give control back to the main event loop which reads
        # the PageKite tunnel, the "ack" packets may build up and cause
        # our ESP32 devices to run out of RAM and break the connection.
        conn.await_data(self.uPK, frame.sid, beware_eof)
        for app_data in iterator:
          for data in buffer_byte_chunks(app_data, self.uPK.SEND_WINDOW_BYTES):
            await fuzzy_sleep_ms(5)
            if saw_eof[0]:
              break

            await conn.reply(frame, data, eof=False)
            sent += len(data)
            # Avoid buffer bloat
            while (progress[0]
                  and not saw_eof[0]
                  and (progress[0] * 1024) < (sent - self.uPK.SEND_WINDOW_BYTES)):
              await fuzzy_sleep_ms(50)
          if saw_eof[0]:
            break

      except Exception as e:
        code = '-'
        want_eof = sent_first
        if not sent_first:
          sent = first_reply(code=500, msg='Server Error', eof=True)
        if self.uPK.debug:
          print_exc(e)
          self.uPK.debug('Exception in async_send_data: %s(%s)' % (type(e), e))
      finally:
        if method != 'HEAD':
          self.log_request(frame, method, path, code, sent, hdrs)
        for fd in _close:
          fd.close()
        if frame.sid in conn.handlers:
          del conn.handlers[frame.sid]
        if want_eof:
          try:
            await conn.reply(frame, None, eof=True)
          except:
            pass

    asyncio.get_event_loop().create_task(async_send_data())
    await fuzzy_sleep_ms(1)

  async def run_handler(self, func, func_attrs, req_env):
    req_env['url_func_attrs'] = func_attrs
    if func_attrs.get('_async'):
      result = await func(req_env)
    else:
      result = func(req_env)

    if result is not None:
      if isinstance(result, dict):
        await fuzzy_sleep_ms(1)
        req_env['send_http_response'](**result)
      else:
        await self.background_send(result,
          req_env['send_http_response'],
          req_env['conn'],
          req_env['frame'],
          req_env['http_headers']['_method'],
          req_env['http_headers']['_pathqs'],
          req_env['http_headers'])

  def get_handler(self, path, headers):
    return _HANDLERS.get(path, (None, None))

  async def handle_http_request(self, kite, conn, frame):
    method = path = '-'
    self.uPK.GC_COLLECT()
    try:
      headers = frame.payload.split(b'\r\n\r\n', 1)[0]
      request, headers = str(headers, 'latin-1').split('\r\n', 1)
      method, pathqs, http = request.split(' ', 2)
      path = pathqs
      if ('..' in path) or method not in self.METHODS:
        raise ValueError()
      del request
      if method != 'POST':
        frame.payload = b''
      qs = ''
      if '?' in path:
        path, qs = path.split('?', 1)

      # Note: This is done in two passes (list, then dict), otherwise
      #       Micropython may crap out and omit headers.
      headers = [
        l[:128].split(': ', 1) for l in headers.splitlines()
        if self.uPK.PARSE_HTTP_HEADERS.match(l)]
      headers = dict(headers)

    except Exception as e:
      return await self._err(400, 'Invalid request', method, pathqs, conn, frame)

    try:
      func, func_attrs = self.get_handler(path, headers)
      filename = self.webroot + path
    except PermissionError as e:
      ec = e.errno if (e.errno) else 403
      return await self._err(ec, 'Access denied', method, pathqs, conn, frame)

    await fuzzy_sleep_ms()
    if func is None:
      try:
        ls = [l[0] for l in ilistdir(filename)]
        if 'index.py' in ls:
          filename = filename + '/index.py'
        elif 'index.html' in ls:
          filename = filename + '/index.html'
        del ls
      except:
        pass
      try:
        fd = open(filename, 'rb')
      except:
        try:
          filename = self.webroot + '/404.py'
          fd = open(filename, 'rb')
        except:
          return await self._err(
            404, 'Not Found', method, pathqs, conn, frame, headers)
    else:
      fd = None

    postponed = []
    await fuzzy_sleep_ms()
    try:
      def first_reply(
            body='', mimetype='text/html; charset=utf-8',
            code=200, msg='OK', ttl=None, eof=True, hdrs={},
            suppress_log=False):
        rdata = bytes(
          self.http_response(code, msg, mimetype, ttl, hdrs), 'utf-8')
        if body and method != 'HEAD':
          rdata += (
            bytes(body, 'utf-8') if isinstance(body, str) else bytes(body))
        conn.sync_reply(frame, rdata, eof=eof)
        if not suppress_log:
          sent = len(rdata) if eof else '-'
          self.log_request(frame, method, pathqs, code, sent, headers)
        return len(rdata)

      def postpone_action(func, *args, **kwargs):
        postponed.append((func, args, kwargs))

      if func or filename.endswith('.py'):
        headers['_method'] = method
        headers['_pathqs'] = pathqs
        headers['_path'] = path
        headers['_qs'] = self.qs_to_list(qs)
        req_env = {
          'time': time, 'os': os, 'sys': sys, 'json': json,
          'open': upk_open, 'sys_open': open,
          'httpd': self, 'kite': kite, 'conn': conn, 'frame': frame,
          'send_http_response': first_reply,
          'postpone_action': postpone_action,
          'http_headers': headers}
        req_env.update(self.base_env)
        # FIXME: This is a bit dumb.
        req_env['req_env'] = ReqEnv(req_env)
        if fd:
          await fuzzy_sleep_ms(25)
          code = str(fd.read(), 'utf-8')
          self.uPK.GC_COLLECT()
          exec(code, req_env)
        else:
          await fuzzy_sleep_ms()
          await self.run_handler(func, func_attrs, req_env['req_env'])
      else:
        filesize = size(filename)
        await self.background_send(
          _read_fd_iterator(fd, self.uPK.FILE_READ_BYTES,
            first_item={
              'hdrs': {'Content-Length': filesize},
              'suppress_log': (filesize < 102400),
              'mimetype': filename_to_mimetype(filename),
              'ttl': self.static_max_age}),
          first_reply, conn, frame, method, pathqs, headers, _close=[fd])
        fd = None
    except PermissionError as e:
      ec = e.errno if (e.errno) else 403
      return await self._err(ec, 'Access denied', method, pathqs, conn, frame)
    except Exception as e:
      if self.uPK.debug:
        print_exc(e)
        self.uPK.debug('Exception in handle_http_request: %s(%s)' % (type(e), e))
      return await self._err(
        500, 'Server Error', method, pathqs, conn, frame, headers)
    finally:
      if fd is not None:
        fd.close()

    for f, a, kw in postponed:
      await fuzzy_sleep_ms()
      f(*a, **kw)
