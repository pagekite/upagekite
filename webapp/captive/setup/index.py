# This file from the uPageKite distribution is placed in the Public Domain.
# Remix at will!

from upagekite.web import handle_big_request, form_encode

def handler():
  post_data = http_headers['_post_data']

  with open('/bootstrap-config.json', 'rb') as fd:
    settings = json.loads(fd.read())

  wifi_ssid = post_data.val('wifi_ssid', settings.get('ssid', ''))
  wifi_key = post_data.val('wifi_pass', settings.get('key', ''))
  kite_name = post_data.val('kite_name', settings.get('kite_name', ''))
  kite_secret = post_data.val('kite_secret', settings.get('kite_secret', ''))

  wifi_config = ("""\
<table><tr>
  <th>Network</th>
  <td><input name=wifi_ssid type=text placeholder='WiFi Network Name' value=%s></td>
</tr><tr>
  <th>Password</th>
  <td><input name=wifi_pass type=text placeholder='WiFi Password' value=%s></td>
</tr></table>""") % (
    form_encode(wifi_ssid),
    form_encode(wifi_key))

  pagekite_config = ("""\
<table><tr>
  <th>Kite name</th>
  <td><input name=kite_name type=text placeholder='yourkite.pagekite.me' value=%s></td>
</tr><tr>
  <th>Secret</th>
  <td><input name=kite_secret type=text placeholder='your-kite-secret' value=%s></td>
</tr></table>""") % (
    form_encode(kite_name),
    form_encode(kite_secret))

  reboot = False
  if (http_headers['_method'] == 'POST' and
      kite_name and kite_secret and wifi_ssid and wifi_key):
    settings['ssid'] = wifi_ssid
    settings['key'] = wifi_key
    settings['kite_name'] = kite_name
    settings['kite_secret'] = kite_secret
    with open('/bootstrap-config.json', 'wb') as fd:
      fd.write(json.dumps(settings))
    reboot = True
    status_message = """\
<p class=success>
  Saved settings! Your device will reboot in 2 seconds.
</p>
"""

  else:
    status_message = ("""\
<p class=help>
  Your %s needs access to your local WiFi network, as well as
  <a target=_blank href="https://pagekite.net/">PageKite.net</a>
  credentials to work.
</p>
""") % (httpd.uPK.APPNAME,)

  send_http_response(ttl=10, body=("""\
<html><head>
  <link rel=icon href="data:;base64,=">
  <style>
    %s
   form {display: %s}
  </style>
  <title>%s: Configure Your %s</title>
</head><body>
  <h1>Configure Your %s</h1>
  %s
  <form method=post enctype="multipart/form-data">
    <h2>Wi-Fi</h2>
    <div id=wifi>%s</div>
    <h2>PageKite</h2>
    <div id=pagekite>%s</div>
    <input id=submit type=submit value="Save Settings and Reboot">
  </form>
</body></html>""") % (
    open('bootstrap/webroot/default.css').read(),  # Inline the CSS
    'none' if reboot else 'block',
    httpd.uPK.APPNAME,
    httpd.uPK.APPNAME,
    httpd.uPK.APPNAME,
    status_message,
    wifi_config,
    pagekite_config))

  if reboot:
    import time
    import machine
    time.sleep(2)
    machine.reset()

handle_big_request(handler, globals())
