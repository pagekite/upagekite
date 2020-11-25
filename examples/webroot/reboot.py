# FIXME: This would be a good place to demo HTTP authentication?
import time
import machine

send_http_response("""\
<html><head>
  <meta http-equiv="refresh" content="60; url=/">
  <link rel="icon" href="data:;base64,=">
  <style>
%s
  </style>
  <title>upagekite: Rebooting!</title>
  <script>
    var count = 60;
    setInterval(function() {
      document.getElementById('t').innerHTML = (count-- + 's');
    }, 1000);
  </script>
</head><body>
  <h1>Rebooting!</h1>
  <p>Rebooting in 2 seconds... page refresh in <span id=t>60s</span>.</p>
</body></html>
""" % (open('bootstrap/webroot/default.css').read(),))

time.sleep(2)
machine.reset()
