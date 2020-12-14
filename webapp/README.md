# upagekite: Developing web apps

This is a guide to developing simple webapps using the uPageKite
micro-framework.

Contents:

1. [Limitations](#limitations)
2. [Basic app architecture](#basic-app-architecture)
3. [Dynamic content](#dynamic-content)


-----------------------------------------------------------------------
## Limitations

uPagekite includes a very minimal implementation of a web server, which
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

### Subset of HTTP/1.1

The server only supports the most commonly used subset of HTTP/1.1:
there is no fancy encoding, every connection is closed after use and so
forth.

File and form uploads are only supported using the `multipart/form-data`
encoding; uploaded files are streamed directly to the SD card, so they
can exceed available RAM. Other form variables must fit in memory.

JSON-RPC is supported (`application/json` uploads), but the payload MUST
be small enough to fit in the devices free memory.

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

(...work in progress...)


