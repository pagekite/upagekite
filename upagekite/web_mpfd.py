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
from .web import PostVars, ParseNull, parse_hdr

# This should be an efficient state machine for iterating over a buffer,
# yielding each individual line for processing. Line lengths are capped
# and the caller can define a list of strings to stop on.
def _lines(payload, stop=(), maxlen=250, eol=b'\n'):
  total = 0
  try:
    while True:
      end = min(maxlen, payload[0][total:].index(eol))  # Raises ValueError
      ln = payload[0][total:total+end+1]
      yield ln
      total += len(ln)
      if ln in stop:
        break
  except ValueError:
    pass
  payload[0] = payload[0][total:]


class ParseMPFD(ParseNull):
  TEMP_FN = 0

  def __init__(self, *args):
    self.in_header = True
    self.varname = None
    self.payload = {'value': ''}
    ParseNull.__init__(self, *args)  # Last, because parse() depends on the above

  def _tempfile(self):
    for path in ('/tmp', ''):
      try:
        temp_filename = '%s/upload_%d.tmp' % (path, ParseMPFD.TEMP_FN)
        fd = open(temp_filename, 'wb')
        ParseMPFD.TEMP_FN += 1
        ParseMPFD.TEMP_FN %= 4
        return {'temp_filename': temp_filename, 'fd': fd}
      except OSError:
        pass
    raise

  def parse(self):
    post_data = self.headers['_post_data']
    box = [self.frame.payload]
    for line in _lines(box):
      if self.uPK.trace:
        self.uPK.trace('<<%s' % line)

      if (line[:2] == b'--') and line[2:].startswith(bytes(self.attrs['boundary'], 'latin-1')):
        if 'fd' in self.payload:
          self.payload['bytes'] -= 2
          self.payload['fd'].close()
          del self.payload['fd']
        if self.varname:
          if self.payload['value'].endswith('\r\n'):
            self.payload['value'] = self.payload['value'][:-2]
          post_data[self.varname] = self.payload
        self.in_header = True
        self.payload = {'value': ''}

      elif self.in_header:
        if line in (b'\n', b'\r\n'):
          self.in_header = False

        elif line.startswith(b'Content-Disposition:'):
          hname, hval = str(line, 'utf-8').split(':', 1)
          hval, hattrs = parse_hdr(hval.strip())
          self.varname = hattrs['name']
          if 'filename' in hattrs:
            self.payload['value'] = hattrs['filename']
            self.payload['bytes'] = 0
            self.payload.update(self._tempfile())

      else:
        if 'bytes' in self.payload:
          self.payload['bytes'] += len(line)
        if 'fd' in self.payload:
          self.payload['fd'].write(line)
        else:
          self.payload['value'] += str(line, 'utf-8')

    self.frame.payload = box[0]
