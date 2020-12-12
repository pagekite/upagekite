# A dynamically generated web page!
from upagekite.web import handle_big_request

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
   </form>
  </div>
  <p>Request details: %s</p>
</body></html>
""") % (
  open('bootstrap/webroot/default.css').read(),  # Inline the CSS
  kite.name,
  frame.remote_ip,
  http_headers))

handle_big_request(respond, globals())
