# Copyright (C) 2020, The Beanstalks Project ehf. and Bjarni R. Einarsson.
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option)
# any later version.
#
# Commercial licenses are for sale. See the files README.md and COPYING.txt
# for more details.


# Decorator for making functions handle POSTed data
def process_post(max_bytes=None):
  def decorate(func):
    def post_wrapper(req_env):
      uPK = req_env['httpd'].uPK
      def handler():
        try:
          req_env['send_http_response'](**func(req_env))
        except Exception as e:
          if uPK.debug:
            uPK.debug('post_wrapper failed: %s(%s)' % (type(e), e))
          req_env['send_http_response'](code=500, msg='Server Error')
      handle_big_request(handler, req_env, max_bytes=max_bytes)
      return None
    return post_wrapper
  return decorate


def html_encode(txt):
  txt = txt.replace('&', '&amp;')
  txt = txt.replace('<', '&lt;')
  return txt.replace('>', '&gt;')


def form_encode(txt):
  txt = txt.replace('&', '&amp;')
  return '"%s"' % txt.replace('"', '&quot;')


def parse_hdr(hdr):
  # This parser is incorrect for foo="bar; baz"; type variables.
  if ';' in hdr:
    attrs = hdr.split(';')
    hdr = attrs.pop(0)
    attrs = dict(a.strip().split('=', 1) for a in attrs)
    for a in attrs:
      if attrs[a][:1] == attrs[a][-1:] == '"':
        attrs[a] = attrs[a][1:-1]
  else:
    attrs = {}
  return (hdr, attrs)


class PostVars(dict):
  def val(self, name, default=''):
    return self.get(name, {'value': default})['value']


class ParseNull():
  def __init__(self, uPK, frame, headers, attrs):
    self.uPK = uPK
    self.headers = headers
    self.frame = frame
    self.attrs = attrs
    self.parse()

  def parse(self):
    pass


class ParseWFUE(ParseNull):
  def parse(self):
    try:
      from .httpd import HTTPD
      if self.uPK.trace:
        self.uPK.trace('<<%s' % self.frame.payload)
      self.headers['_post_data'] = HTTPD.qs_to_list(
        str(self.frame.payload, 'utf-8'))
      self.frame.payload = b''
    except Exception as e:
      if self.uPK.debug:
        self.uPK.debug('%s parse failed: %s(%s)' % (self, type(e), e))


class ParseJSON(ParseNull):
  def parse(self):
    try:
      import json
      if self.uPK.trace:
        self.uPK.trace('<<%s' % self.frame.payload)
      self.headers['_post_data'] = json.loads(self.frame.payload)
      self.frame.payload = b''
    except Exception as e:
      if self.uPK.debug:
        self.uPK.debug('%s parse failed: %s(%s)' % (self, type(e), e))


def handle_big_request(handler, env, max_bytes=None):
  uPK = env['httpd'].uPK
  frame = env['frame']
  if frame.payload:
    hdr, frame.payload = frame.payload.split(b'\r\n\r\n', 1)
    if uPK.trace:
      uPK.trace('<<%s' % (hdr + b'\r\n\r\n',))
    del hdr

  # Help our devs out a bit.
  if uPK.debug and max_bytes and (max_bytes > uPK.MAX_POST_BYTES):
    uPK.debug('BUG: max_bytes(%d) > MAX_POST_BYTES(%d), ignoring max_bytes'
      % (max_bytes, uPK.MAX_POST_BYTES))

  # This has to happen before we let the parser run, as parsers often
  # modify the frame.payload: in-place mutations are how we cope with
  # our memory constraints.
  headers = env['http_headers']
  max_bytes = min(max_bytes or uPK.MAX_POST_BYTES, uPK.MAX_POST_BYTES)
  needed_bytes = int(headers.get('Content-Length', 0)) - len(frame.payload)
  if needed_bytes > max_bytes:
    return env['send_http_response'](code=400, msg='Too big')

  (ctype, cattrs) = parse_hdr(headers.get('Content-Type', 'text/plain'))
  if ctype == 'application/json':
    parser_cls = ParseJSON
  elif ctype == 'application/x-www-form-urlencoded':
    parser_cls = ParseWFUE
  elif ctype == 'multipart/form-data':
    from .web_mpfd import ParseMPFD
    parser_cls = ParseMPFD
  else:
    parser_cls = ParseNull

  headers['_post_data'] = PostVars()
  parser = parser_cls(uPK, frame, headers, cattrs)
  uPK.GC_COLLECT()
  if not needed_bytes:
    del parser
    return handler()

  conn = env['conn']
  needed_bytes = [needed_bytes]  # Scope hack, nonlocal does not work
  def update_frame(frameN):
    nbytes = len(frameN.payload or '')
    frame.payload += frameN.payload
    needed_bytes[0] -= len(frameN.payload)
    del frameN

    parser.parse()
    uPK.GC_COLLECT()
    if nbytes < 1 or needed_bytes[0] < 1:
      if frame.sid in conn.handlers:
        del conn.handlers[frame.sid]
      if uPK.trace and frame.payload:
        uPK.trace('<<%s' % frame.payload)
      handler()
  conn.await_data(uPK, frame.sid, update_frame, needed_bytes[0])
