# upagekite: Developing web apps

This is a guide to developing simple webapps using the uPageKite
micro-framework.

Contents:

1. [Limitations](#limitations)
2. [Basic app architecture](#basic-app-architecture)
3. [Dynamic content](#dynamic-content)
4. [Periodic jobs](#periodic-jobs)


-----------------------------------------------------------------------
## Limitations

uPageKite includes a very minimal implementation of a web server, which
is designed to run under tight memory constraints on embedded hardware.

This is a brief summary of the main differences between uPageKite
development and using other web servers and frameworks. 

### One thread, one request

The web server is single-threaded and will (by default) only process one
request at a time. This is generally not a problem when serving small
files, but note that serving large content will block the web server and
prevent any other work from getting done.

Ideally, every response should be small enough to fit in one or two
TCP/IP packets (<3000 bytes).

In general, the uPageKite code is written to minimize memory use, even
if that requires using more CPU cycles. Speed was not a design goal.

### Subset of HTTP/1.1

The server only supports a simple subset of HTTP/1.1: there is no fancy
encoding, every connection is closed after use and so forth.

File and form uploads are only supported using the `multipart/form-data`
encoding; uploaded files are streamed directly to the SD card, so they
can exceed available RAM. Other form variables must fit in memory.

JSON-RPC is supported (`application/json` uploads), but the payload MUST
be small enough to simultaneously fit in the device's free memory raw
and decoded.

### Limited security

uPageKite does not provide its own TLS server; it relies on the PageKite
relay for TLS and may thus be vulnerable to eavesdropping or
man-in-the-middle attacks at the relay.

The connection to the relay is (by default) encrypted to prevent
eavesdropping, but as the certificates are currently not validated,
man-in-the-middle attacks on the network segments between the device and
the PageKite relay may pose a risk.

### Python only!

The uPageKite framework does not support development in any languages
other than (Micro)Python on the device and HTML/Javascript on the
client.

Although it would theoretically be possible to proxy requests to an
external process, in practice this would quickly exhaust the available
RAM on the target devices.

### Barely a framework

Calling uPageKite a web development framework is a slight exaggeration.
The package provides:

* A functioning web server
* A recommended structure for your app
* Helper functions for decoding and handling common HTTP requests
* Helper code for implementing captive portals
* Helper code for downloading code updates from the web


-----------------------------------------------------------------------
## Basic app architecture

The structure of the sample uPageKite webapp looks like this:

    bootstrap.json 
    webapp/
    |
    |-- stage_2.py
    |-- webroot/
    |   |- default.css
    |   |- hello/
    |   |  `- index.html
    |   |- index.py
    |   |- post.py
    |   `- reboot.py
    ...


The file `bootstrap.json` tells the bootstrapping logic which files
to download and install to the device. This is covered in the [main
project README.md](../README.md).

The [`stage_2.py`](stage_2.py) script is the main entry point of the
app; it takes care of configuring and launching `upagekite`. It should
be well commented.

The application logic and site content is in the `webroot/` directory,
and the URLs exposed follow the same structure.

Unlike many modern web frameworks, uPageKite does not have a "request
route" concept, it simply maps URLs directly to files and directories
under `webroot/`. As is customary with Apache and other mainstream web
servers, if an URL would map to a directory instead of a file, the
request will be routed to a file named `index.html` or `index.py` in
that directory.

Examples:

    http://dev.pagekite.me/         -> webapp/webroot/index.py
    http://dev.pagekite.me/index.py -> webapp/webroot/index.py
    http://dev.pagekite.me/hello    -> webapp/webroot/hello/index.html

Publishing static content is thus trivial; simply place the file in the
right directory and add it to your `bootstrap.json`.

Dynamic content (web APIs included) is discussed in the next section.


-----------------------------------------------------------------------
## Dynamic content

To create dynamic API endpoints or web pages, it is most elegant to
create a directory structure under `webroot/` with the path you want,
and an `index.py` file at the right point:

    # Create https://device.pagekite.me/api/v1/reboot/
    mkdir -p webapp/webroot/api/v1/reboot/
    touch webapp/webroot/api/v1/reboot/index.py

Dynamic endpoints can have any name ending in `.py`, but if the name
is not `index.py` then the filename must be included in the URL.

    # Create https://device.pagekite.me/api/v1/reset/factory.py
    mkdir -p webapp/webroot/api/v1/reboot/
    touch webapp/webroot/api/v1/reset/factory.py

(You will also need to add a matching entry to your `bootstrap.json`
file, if you are using the uPageKite bootstrapping system.)

### GET-only endpoints

**WARNING:** THIS MIGHT STILL CHANGE!

The pattern for creating GET-only endpoints is very simple; a basic
API endpoint which provides JSON-formatted data might look something
like this:

    # Copyright (C) 2020, Foocorp Supergadgets
    # A Useful Comment
    #
    import yourlib
    import json
    
    response_data = json.dumps({
        'version': yourlib.API_VERSION,
        'data': yourlib.get_sensor_readings()
    })
    
    # Most arguments can be omitted, the defaults are sane!
    send_http_response(
        ttl=120,                     # Default: None, no Cache-Control
        code=200,                    # Default: 200
        msg=OK,                      # Default: OK
        eof=True,                    # Default: True, close after send
        hdrs={'X-Foo': 'Magic'},     # Default: None, no extra headers
        mimetype='application/json', # Default: text/html; charset=utf-8
        body=response_data           # Default: No message body
    )

Endpoints following this pattern will completely ignore any uploaded
form data, but can be accessed using GET, HEAD and POST.


### POST-enabled endpoints

**WARNING:** THIS MIGHT STILL CHANGE!

The pattern for creating endpoints which accept POSTed data is similar
to the GET-only method above, but instead of directly calling
`send_http_response` directly, the response logic is wrapped in a
function which is passed to `handle_big_request` for execution once the
POSTed data has been received and parsed.

The posted data will be decoded and added to the global `http_headers`
variable so your code can make use of it.

    # Copyright (C) 2020, Foocorp Supergadgets
    # A Useful Comment
    #
    from upagekite.web import handle_big_request
    import yourlib
    import json

    def handler():
        response_data = json.dumps({
            'version': yourlib.API_VERSION,
            'data': yourlib.get_sensor_readings()
        })
    
        send_http_response(
            ttl=120,
            mimetype='application/json',
            body=response_data
        )

    handle_big_request(handler, globals())


(...work in progress...)


-----------------------------------------------------------------------
## Access controls and authentication


    from upagekite.web import access_requires

    ...

    access_requires(req_env,
        methods=('GET', 'POST'),   # Disallowing GET is often smart
        local=False,               # Set true to allow only localhost clients
        secure_transport=True,     # Require localhost or TLS
        auth='basic')              # Require HTTP basic Auth


-----------------------------------------------------------------------
## Periodic jobs
        
(...work in progress...)


