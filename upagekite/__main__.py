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
import sys

from . import Kite, uPageKite, uPageKiteDefaults


class MyDefaults(uPageKiteDefaults):
  # Disable connecting to new front-ends, static setup
  #FE_NAME = None

  # Enable all the logging
  trace = uPageKiteDefaults.log
  debug = uPageKiteDefaults.log
  info  = uPageKiteDefaults.log
  error = uPageKiteDefaults.log


async def handle_http_request(kite, conn, frame):
  await conn.reply(frame, (
      'HTTP/1.0 200 OK\n'
      'Content-Type: text/html\n'
      '\n'
      '<h1>Hello world!</h1><h2>This is %s, you are %s</h2>\n'
    ) % (kite.name, frame.remote_ip))


if __name__ == "__main__":
  try:
    uPageKite([
        Kite(sys.argv[1], sys.argv[2], handler=handle_http_request)
      ], uPK=MyDefaults).run()
  except IndexError:
    print('Usage: %s kitename kitesecret' % sys.argv[0])
