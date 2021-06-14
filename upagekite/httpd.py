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
import os
import sys
import time
import json

from .proto import ilistdir, fuzzy_sleep_ms


_HANDLERS_SYNC = {}
_HANDLERS_ASYNC = {}


# Decorators for registering functions as URL handlers
def url(*paths):
    def decorate(func):
        for path in paths:
            _HANDLERS_SYNC[path] = func
        return func
    return decorate


def async_url(*paths):
    def decorate(func):
        for path in paths:
            _HANDLERS_ASYNC[path] = func
        return func
    return decorate


# Helper class for navigating the request environment
class ReqEnv(dict):
    # Details about the client
    remote_ip = property(lambda s: s['frame'].remote_ip)

    # Details about the HTTP request
    query_vars = property(lambda s: dict(s['http_headers']['_qs']))
    query_tuples = property(lambda s: s['http_headers']['_qs'])
    request_path = property(lambda s: s['http_headers']['_path'])
    http_method = property(lambda s: s['http_headers']['_method'])
    http_headers = property(lambda s: s['http_headers'])
    http_host = property(lambda s: s['frame'].host)
    http_port = property(lambda s: s['frame'].port)


class HTTPD:
  METHODS = (
    'GET',
    'HEAD',
    'POST')
  MIMETYPES = {
    'css': 'text/css',
    'gif': 'image/gif',
    'htm': 'text/html; charset=utf-8',
    'html': 'text/html; charset=utf-8',
    'jpg': 'image/jpeg',
    'jpeg': 'image/jpeg',
    'json': 'application/json',
    'md': 'text/plain; charset=utf-8',
    'pdf': 'application/pdf',
    'txt': 'text/plain; charset=utf-8',
    '_': 'application/octet-stream'}

  def __init__(self, name, webroot, env, uPK):
    self.uPK = uPK
    self.name = name
    self.webroot = webroot
    self.static_max_age = 3600
    self.base_env = env

  @classmethod
  def unquote(cls, quoted):
    if isinstance(quoted, str):
      quoted = bytes(quoted, 'latin-1')
    _in = quoted.split(b'%')
    _out = [_in[0]]
    for frag in _in[1:]:
      try:
        _out.extend([bytes([int(frag[:2], 16)]), frag[2:]])
      except ValueError:
        _out.extend([b'%', frag])
    try:
      return str(b''.join(_out), 'utf-8')
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
    return (
        'HTTP/1.0 %d %s\r\n'
        'Server: %s\r\n'
        'Content-Type: %s\r\n'
        '%s%s\r\n'
      ) % (
        code, msg, self.uPK.APPURL, mimetype,
        ('Cache-Control: max-age=%d\r\n' % ttl) if ttl else '',
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
    await conn.reply(frame, self.http_response(code, msg, 'text/plain')+msg+'\n')

  def _mimetype(self, fn):
    return self.MIMETYPES.get(fn.rsplit('.', 1)[-1], self.MIMETYPES['_'])

  async def handle_http_request(self, kite, conn, frame):
    # FIXME: Should set up a state machine to handle multi-frame or
    #        long running requests. This is just one-shot for now.
    method = path = '-'
    try:
      headers = frame.payload.split(b'\r\n\r\n', 1)[0]
      request, headers = str(headers, 'latin-1').split('\r\n', 1)
      method, path, http = request.split(' ', 2)
      if ('..' in path) or method not in self.METHODS:
        raise ValueError()
      del request
      if method != 'POST':
        frame.payload = b''
      qs = ''
      if '?' in path:
        path, qs = path.split('?', 1)
      headers = dict(
        l[:128].split(': ', 1) for l in headers.splitlines()
        if self.uPK.PARSE_HTTP_HEADERS.match(l))
    except Exception as e:
      return await self._err(400, 'Invalid request', method, path, conn, frame)

    func = _HANDLERS_SYNC.get(path)
    func_async = _HANDLERS_ASYNC.get(path)
    filename = self.webroot + path

    await fuzzy_sleep_ms()
    if func is None and func_async is None:
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
        fd = open(filename, 'r')
      except:
        try:
          filename = self.webroot + '/404.py'
          fd = open(filename, 'r')
        except:
          return await self._err(404, 'Not Found', method, path, conn, frame, headers)
    else:
      fd = None

    postponed = []
    await fuzzy_sleep_ms()
    try:
      if func or func_async or filename.endswith('.py'):
        replies = []
        def r(body='', mimetype='text/html; charset=utf-8',
              code=200, msg='OK', ttl=None, eof=True, hdrs={}):
          rdata = self.http_response(code, msg, mimetype, ttl, hdrs)
          if method != 'HEAD':
            rdata += body
          conn.sync_reply(frame, rdata, eof=eof)
          self.log_request(frame, method, path, code, len(rdata), headers)
        def p(func, *args, **kwargs):
          postponed.append((func, args, kwargs))
        headers['_method'] = method
        headers['_path'] = path
        headers['_qs'] = self.qs_to_list(qs)
        req_env = ReqEnv({
          'time': time, 'os': os, 'sys': sys, 'json': json,
          'httpd': self, 'kite': kite, 'conn': conn, 'frame': frame,
          'send_http_response': r,
          'postpone_action': p,
          'http_headers': headers})
        req_env.update(self.base_env)
        if fd:
          await fuzzy_sleep_ms(25)
          exec(fd.read(), req_env)
        else:
          await fuzzy_sleep_ms()
          if func:
            result = func(req_env)
          else:
            result = await func_async(req_env)
          if result:
            await fuzzy_sleep_ms()
            r(**result)

      else:
        mimetype = self._mimetype(filename)
        resp = self.http_response(200, 'OK', mimetype, self.static_max_age)
        await conn.reply(frame, resp, eof=False)
        sent = len(resp)
        while method != 'HEAD':
          await fuzzy_sleep_ms()
          data = fd.read(4096)
          if data:
            sent += len(data)
            await conn.reply(frame, data, eof=False)
          else:
            await conn.reply(frame, eof=True)
            break
        self.log_request(frame, method, path, 200, sent, headers)
    except Exception as e:
      print('Exception: %s' % e)
      return await self._err(500, 'Server Error', method, path, conn, frame, headers)
    finally:
      if fd is not None:
        fd.close()

    for f, a, kw in postponed:
      await fuzzy_sleep_ms()
      f(*a, **kw)
