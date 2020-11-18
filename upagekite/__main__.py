import sys

from . import Kite, uPageKite, uPageKiteDefaults


class MyProto(uPageKiteDefaults):
  # Disable connecting to new front-ends, static setup
  #FE_NAME = None

  # Enable all the logging
  trace = uPageKiteDefaults.log
  debug = uPageKiteDefaults.log
  info  = uPageKiteDefaults.log
  error = uPageKiteDefaults.log


def handle_http_request(kite, conn, frame):
  conn.reply(frame, (
      'HTTP/1.0 200 OK\n'
      'Content-Type: text/html\n'
      '\n'
      '<h1>Hello world!</h1><h2>This is %s, you are %s</h2>\n'
    ) % (kite.name, frame.remote_ip))


if __name__ == "__main__":
  try:
    uPageKite([
        Kite(sys.argv[1], sys.argv[2], handler=handle_http_request)
      ], proto=MyProto).run()
  except IndexError:
    print('Usage: %s kitename kitesecret' % sys.argv[0])
