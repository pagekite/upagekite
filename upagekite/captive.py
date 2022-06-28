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
from .proto import socket


class DNSQuery:
  def __init__(self, data):
    self.query = data
    self.qdomain = ''
    if ((data[2] >> 3) & 15) == 0:
      ppos = 12
      plen = data[ppos]
      while plen:
        ppos += 1
        self.qdomain += str(data[ppos:ppos+plen], 'latin-1') + '.'
        ppos += plen
        plen = data[ppos]
    ppos += 1
    self.qend = ppos + 4
    self.qtype = ('IN A'
      if (data[ppos:self.qend] == b"\x00\x01\x00\x01")
      else 'unknown')

  def response(self, ip):
    if self.qtype == 'IN A':
      flags = b"\x81\x80"
      answers = b"\x00\x01"
      response = (b''
        + self.query[12:self.qend]  # Question, again
        + b"\x00\x00\x00\x01"       # TTL=1s
        + b"\x00\x04"               # RDLENGTH=4
        + ip)
    else:
      flags = b"\x81\x82"  # SERVFAIL
      answers = b"\x00\x00"
      response = b''

    return (b''
      + self.query[:2]            # Identification
      + flags
      + b"\x00\x01"               # Questions: 1
      + answers
      + b"\x00\x00\x00\x00"       # Auth: 0, Additional: 0
      + self.query[12:self.qend]  # Original question
      + response)


class CDNS:
  def __init__(self, ip, port):
    self.ip = bytes(map(int, ip.split(".")))
    self.fd = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    self.fd.setblocking(False)
    self.fd.bind(socket.getaddrinfo('0.0.0.0', port)[0][-1])

  async def process_io(self, uPK):
    try:
      data, addr = self.fd.recvfrom(4096)
      query = DNSQuery(data)
      if query.qdomain:
        if uPK.info:
          uPK.info('[dns] Responding to %s query from %s for %s'
            % (query.qtype, addr[0], query.qdomain))
        self.fd.sendto(query.response(self.ip), addr)
      elif uPK.debug:
        uPK.debug('[dns] Unparsed query from %s: %s' % (addr[0], data))

    except Exception as e:
      print('Oops in CDNS: %s' % e)

    return True
