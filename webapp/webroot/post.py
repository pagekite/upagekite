# This file from the uPageKite distribution is placed in the Public Domain.
# Remix at will!

from upagekite.web import csrf_input, handle_big_request, access_requires

def respond():
  send_http_response(
    ttl=120, code=200, mimetype='text/html; charset=utf-8',
    body=("""\
<html><head>
  <link rel="icon" href="data:;base64,=">
  <style>
%s
  </style>
  <title>upagekite: File upload test</title>
</head><body>
  <h1>Hello world!</h1>
  <p>This is <b>%s</b>, you are %s</p>
  <div>
   <form method="post" enctype="multipart/form-data">
    Select something to upload:
    <input type="file" name="upload"><br>
    <input type="text" name="comments"><br>
    <input type="submit" value="Upload" name="submit">
    %s
   </form>
  </div>
  <p>[ <a href="/">back to top</a> ]</p>
  <p>Request details: %s</p>
</body></html>
""") % (
  open('/webroot/default.css').read(),  # Inline the CSS
  kite.name,
  frame.remote_ip,
  csrf_input(),
  http_headers))

access_requires(req_env, methods=('GET', 'POST'))
handle_big_request(respond, globals())
