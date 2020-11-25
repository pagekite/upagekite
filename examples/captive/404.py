send_http_response(code=307, ttl=1, hdrs={
  'Location': 'http://%s/setup/' % app['proto'].APPNAME})
