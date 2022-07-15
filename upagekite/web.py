# Copyright (C) 2020-2022, The Beanstalks Project ehf. and Bjarni R. Einarsson.
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option)
# any later version.
#
# Commercial licenses are for sale. See the files README.md and COPYING.txt
# for more details.

try:
  from ubinascii import a2b_base64, b2a_base64
except (NameError, ImportError):
  from binascii import a2b_base64, b2a_base64


from .proto import random_bytes, asyncio, PermissionError


CSRF_CODES = []
CSRF_MAX = 30

def csrf_value():
    global CSRF_CODES
    secret = str(b2a_base64(random_bytes(8)), 'utf-8').strip().replace('=', '')
    CSRF_CODES = CSRF_CODES[-CSRF_MAX:]
    CSRF_CODES.append(secret)
    return secret

def csrf_input():
    return '<input type="hidden" name="upk_csrf" value="%s">' % csrf_value()


# Decorator for making functions handle POSTed data
def process_post(max_bytes=None, _async=False, csrf=True):
  def decorate(func):
    def post_wrapper(req_env):
      func_attrs = req_env['url_func_attrs']
      httpd = req_env['httpd']
      async def handler():
        try:
          await httpd.run_handler(func, func_attrs, req_env)
        except Exception as e:
          if httpd.uPK.debug:
            httpd.uPK.debug('post_wrapper failed: %s(%s)' % (type(e), e))
          req_env['send_http_response'](code=500, msg='Server Error')
      handle_big_request(handler, req_env,
          max_bytes=max_bytes, _async=True, csrf=csrf)
    if _async:
      async def async_post_wrapper(req_env):
        return post_wrapper(req_env)
      return async_post_wrapper
    else:
      return post_wrapper
  return decorate


def _parse_basic_auth(data):
  return tuple(str(a2b_base64(data), 'utf-8').split(':', 1))


def access_requires(req_env,
    methods=None,
    local=False,
    secure_transport=False,
    csrf=True,
    auth=False,
    auth_check=None,
    ip_check=None):
  """
  Require the connection fulfill certain criteria, raising a PermissionError
  otherwise. As a side effect, this method will parse the Authorization
  header and set req_env['auth_bearer'] or req_env['auth_basic'] if present.

  Requesting a secure transport requires the connection either originate
  on localhost or use TLS encryption.

  The auth_check and ip_check arguments, if provided, are functions which
  can be used to validate the provided Authorization data, or the remote
  IP address respectively. They should return True if access is granted.

  They are invoked as auth_check(method, data) and ip_check(remote_ip).

  If the Authorization method is 'basic', the data is a (username, password)
  pair. Otherwise it is the raw data from the Authorization HTTP header.

  This method can discable CSRF checks for HTTP POST uploads, which are
  otherwise enabled by default.
  """
  if methods and (req_env.http_method not in methods):
    raise PermissionError('Unsupported method')

  if (local or secure_transport) and not req_env.is_local:
    if local:
      raise PermissionError(
        'Method is localhost-only, got %s' % req_env.remote_ip)
    if secure_transport and not req_env.frame.tls:
      raise PermissionError('Method requires TLS or localhost')

  if ip_check is not None and not ip_check(req_env.remote_ip):
    raise PermissionError('Access denied')

  # This check is deferred until POSTed data has been parsed
  req_env['_csrf_disabled'] = not (csrf and req_env.http_method == 'POST')

  # Setting the code to 401, prompts the error handling code to add the
  # WWW-Authentication header to the response, so users can log in.
  code = 401 if ('basic' in (auth or '')) else 403
  if 'Authorization' in req_env.http_headers:
    try:
      meth, data = req_env.http_headers['Authorization'].split(' ', 1)
      meth = meth.strip().lower()
      if auth and (meth not in auth):
        raise PermissionError(code, 'Invalid authorization')

      data = data.strip()
      if meth == 'basic':
        data = _parse_basic_auth(data)

      req_env['auth_%s' % meth] = data
      if auth_check is not None and not auth_check(meth, data):
        raise PermissionError(code, 'Invalid authorization')
    except PermissionError:
      raise
    except:
      raise PermissionError(code, 'Invalid authorization')
  elif auth:
    raise PermissionError(code, 'No authorization found')


# Decorator for performing basic access controls
def http_require(
    methods=None,
    local=False,
    secure_transport=False,
    csrf=True,
    auth=False,
    auth_check=None,
    ip_check=None):
  """
  Decorate an URL handler with access requirements. See require() for details.
  """
  def decorate(func):
    def http_require_wrapper(req_env):
      access_requires(req_env,
        methods, local, secure_transport, csrf, auth, auth_check, ip_check)
      return func(req_env)
    return http_require_wrapper
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


def handle_big_request(handler, env, max_bytes=None, _async=False, csrf=True):
  uPK = env['httpd'].uPK
  frame = env['frame']
  req_env = env['req_env']

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
    env['send_http_response'](code=400, msg='Too big')
    return None

  (ctype, cattrs) = parse_hdr(headers.get('Content-Type', 'text/plain'))
  if ctype == 'application/json':
    parser_cls = ParseJSON
    csrf = False
  elif ctype == 'application/x-www-form-urlencoded':
    parser_cls = ParseWFUE
  elif ctype == 'multipart/form-data':
    from .web_mpfd import ParseMPFD
    parser_cls = ParseMPFD
  else:
    parser_cls = ParseNull

  if req_env.http_method in ('GET', 'HEAD', 'OPTIONS'):
    needed_bytes = 0
    csrf = False

  def check_csrf():
    if csrf and not req_env.get('_csrf_disabled'):
      cc = req_env.post_vars.get('upk_csrf', None)
      cc = cc['value'] if isinstance(cc, dict) else cc
      if not cc or cc not in CSRF_CODES:
        env['send_http_response'](code=403, msg='Invalid CSRF')
        return False
    return True

  headers['_post_data'] = PostVars()
  parser = parser_cls(uPK, frame, headers, cattrs)
  uPK.GC_COLLECT()
  if not needed_bytes:
    del parser
    if check_csrf():
      if _async:
        asyncio.get_event_loop().create_task(handler())
      else:
        handler()
    return None

  conn = env['conn']
  needed_bytes = [needed_bytes]  # Scope hack, nonlocal does not work
  async def update_frame(frameN):
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
      if check_csrf():
        if _async:
          await handler()
        else:
          handler()

  conn.async_await_data(uPK, frame.sid, update_frame, needed_bytes[0])
  return None
