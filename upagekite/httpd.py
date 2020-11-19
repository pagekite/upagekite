# Copyright (C) 2020, The Beanstalks Project ehf. and Bjarni R. Einarsson.
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or (at
# your option) any later version.
#
# See the files README.md and COPYING.txt for more details.
#
import os
import sys
import time
import json


class HTTPD:
  def __init__(self, name, webroot):
    self.name = name
    self.webroot = webroot

  def _err(self, code, msg, conn, frame):
      conn.reply(frame, (
          'HTTP/1.0 %d %s\r\n'
          'Content-Type: text/plain\r\n'
          '\r\n%s\r\n'
        ) % (code, msg, msg))

  def handle_http_request(self, kite, conn, frame):
    try:
      request, headers = str(frame.payload, 'latin-1').split('\r\n', 1)
      method, path, http = request.split(' ', 2)
      if '..' in path:
        raise ValueError()
      qs = ''
      if '?' in path:
        path, qs = path.split('?', 1)
      headers = dict(l.split(': ', 1) for l in headers.splitlines() if l)
      filename = self.webroot + path
    except Exception as e:
      print('%s: %s' % (filename, e))
      return self._err(400, 'Invalid request', conn, frame)

    try:
      ls = os.listdir(filename)
      if 'index.py' in ls:
        filename = filename + '/index.py'
      elif 'index.html' in ls:
        filename = filename + '/index.html'
    except:
      pass
    try:
      fd = open(filename, 'r')
    except Exception as e:
      print('%s: %s' % (filename, e))
      return self._err(404, 'Not Found', conn, frame)

    try:
      if filename.endswith('.py'): 
        exec(fd.read(), {
          'time': time, 'os': os, 'sys': sys, 'json': json,
          'httpd': self,
          'kite': kite, 'conn': conn, 'frame': frame})
      else:
        mimetype = 'text/html'  # FIXME
        conn.reply(frame, (
            'HTTP/1.0 200 OK\r\n'
            'Content-Type: %s\r\n'
            '\r\n'
          ) % (mimetype,),
          eof=False)
        while True:
          data = fd.read(4096)
          if data:
            conn.reply(frame, data, eof=False)
          else:
            conn.reply(frame, eof=True)
            break
    except Exception as e:
      print('%s: %s' % (filename, e))
      return self._err(500, 'Internal Error', conn, frame)
    finally:
      fd.close()
