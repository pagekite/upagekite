# Copyright (C) 2020, The Beanstalks Project ehf. and Bjarni R. Einarsson.
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or (at
# your option) any later version.
#
# See the files README.md and COPYING.txt for more details.
#
import upagekite
import upagekite.httpd
import time
try:
  from boot import settings
except:
  settings = {}


print("=2= Stage two (sample) loaded successfully!")


class MyProto(upagekite.uPageKiteDefaults):
  #trace = upagekite.uPageKiteDefaults.log
  debug = upagekite.uPageKiteDefaults.log
  info  = upagekite.uPageKiteDefaults.log
  error = upagekite.uPageKiteDefaults.log


if settings.get('kite_name') and settings.get('kite_secret'):
  # These are things we want visible within the individual page scripts
  # run for dynamic HTTP requests. Setting this allows code to consult
  # global settings, which could become a security leak.
  env = {'app': {'proto': MyProto, 'settings': settings}}

  httpd = upagekite.httpd.HTTPD(
    settings['kite_name'],
    '/bootstrap/webroot',
    env,
    MyProto)

  kite = upagekite.Kite(
    settings['kite_name'],
    settings['kite_secret'],
    handler=httpd.handle_http_request)

  print("=2= Launching uPageKite Hello World: http://%s" % kite.name)
  print("=2= Press CTRL+C to abort and drop to REPL")
  print()
  time.sleep(2)

  upk = upagekite.uPageKite([kite], proto=MyProto)
  env['app']['upagekite'] = upk  # Expose to page logic
  upk.run()

else:
  try:
    import webrepl
    print("=2= No PageKite credentials, launching webrepl instead.")
    webrepl.start()
  except:
    print("=2= No PageKite credentials, no webrepl. I give up!")
