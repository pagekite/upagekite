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

from .proto import ilistdir


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

  def __init__(self, name, webroot, env, proto):
    self.proto = proto
    self.name = name
    self.webroot = webroot
    self.static_max_age = 3600
    self.base_env = env

  def http_response(self, code, msg, mimetype, ttl=None, hdrs={}):
    return (
        'HTTP/1.0 %d %s\r\n'
        'Server: %s\r\n'
        'Content-Type: %s\r\n'
        '%s%s\r\n'
      ) % (
        code, msg, self.proto.APPURL, mimetype,
        ('Cache-Control: max-age=%d\r\n' % ttl) if ttl else '',
        ''.join('%s: %s\r\n' % (k, v) for k, v in hdrs.items()))

  def log_request(self, frame, method, path, code,
                  sent='-', headers={}, user='-'):
    if self.proto.info:
      self.proto.info('[HTTPD] %s %s - %s %s:%s%s - %s %s - %s' % (
        user, frame.remote_ip,
        method, frame.host, frame.port, path,
        code, sent,
        headers.get('User-Agent', headers.get('user-agent', '-'))))

  def _err(self, code, msg, method, path, conn, frame, headers={}):
    self.log_request(frame, method, path, code, headers=headers)
    conn.reply(frame, self.http_response(code, msg, 'text/plain')+msg+'\n')

  def _mimetype(self, fn):
    return self.MIMETYPES.get(fn.rsplit('.', 1)[-1], self.MIMETYPES['_'])

  def handle_http_request(self, kite, conn, frame):
    # FIXME: Should set up a state machine to handle multi-frame or
    #        long running requests. This is just one-shot for now.
    method = path = '-'
    try:
      request, headers = str(frame.payload, 'latin-1').split('\r\n', 1)
      method, path, http = request.split(' ', 2)
      if ('..' in path) or method not in self.METHODS:
        raise ValueError()
      del frame.payload
      del request
      qs = ''
      if '?' in path:
        path, qs = path.split('?', 1)
      headers = dict(
        l[:128].split(': ', 1) for l in headers.splitlines()
        if self.proto.PARSE_HTTP_HEADERS.match(l))
      filename = self.webroot + path
    except Exception as e:
      return self._err(400, 'Invalid request', method, path, conn, frame)

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
        return self._err(404, 'Not Found', method, path, conn, frame, headers)

    try:
      if filename.endswith('.py'): 
        def r(body='', mimetype='text/html; charset=utf-8',
              code=200, msg='OK', ttl=None, hdrs={}):
          rdata = self.http_response(code, msg, mimetype, ttl, hdrs)
          if method != 'HEAD':
            rdata += body
          conn.reply(frame, rdata)
          self.log_request(frame, method, path, code, len(rdata), headers)
        headers['_method'] = method
        headers['_path'] = path
        headers['_qs'] = qs
        req_env = {
          'time': time, 'os': os, 'sys': sys, 'json': json,
          'httpd': self, 'send_http_response': r,
          'kite': kite, 'conn': conn, 'frame': frame,
          'http_headers': headers}
        req_env.update(self.base_env)
        exec(fd.read(), req_env)
      else:
        mimetype = self._mimetype(filename)
        resp = self.http_response(200, 'OK', mimetype, self.static_max_age)
        conn.reply(frame, resp, eof=False)
        sent = len(resp)
        while method != 'HEAD':
          data = fd.read(4096)
          if data:
            sent += len(data)
            conn.reply(frame, data, eof=False)
          else:
            conn.reply(frame, eof=True)
            break
        self.log_request(frame, method, path, 200, sent, headers)
    except Exception as e:
      print('Exception: %s' % e)
      return self._err(500, 'Server Error', method, path, conn, frame, headers)
    finally:
      fd.close()
