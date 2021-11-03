# upagekite: MicroPython/ESP32 PageKite web server

This code makes it very easy to create static web sites or simple web
services in MicroPython, and automatically punch through firewalls and
NAT to make the server reachable from the wider Internet.

This is a minimal HTTP server and PageKite implementation, written for
use with MicroPython on the ESP32. It is also tested on Ubuntu/Python
3.7 and Ubuntu's MicroPython snap. You will need access to a PageKite
relay, such as those provided by [pagekite.net](https://pagekite.net/).


**WARNING:** This code does not magically make the ESP32 suitable for
hosting a high-volume webapp. Not does it "solve" security. Be careful!

**WARNING:** This is ALPHA QUALITY CODE. [Get in
touch](https://pagekite.net/support/chat/) and have a chat before using
it for anything important! Here be dragons!


## Hacking uHowTo

1. Clone this repo: `git clone https://github.com/pagekite/upagekite/`
2. Follow the **Bootstrapping Development** guide below
3. Make your changes to [stage_2.py](webapp/stage_2.py)
4. Create your webapp (see [webapp/webroot](webapp/webroot/))
5. Add new code files to "mirror" in [bootstrap.json](bootstrap.json)
6. Iterate!

Consult [webapp/README.md](webapp/README.md) for guidance on how to
develop simple web apps or APIs using this framework.


## Project Status

### Works:

* Exposing a hello-world webapp via. [pagekite.net](https://pagekite.net/)
* Network-based bootstrapping, load & run code from the web
* Tested platforms and pythons:
   * MicroPython 1.13 on an ESP32-WROOM-32 DevKitC board
   * MicroPython 1.13 on Ubuntu Linux
   * Python 3.7.5 on Ubuntu Linux
* Adaptive relay selection (ESP32 relies on DNS hints from web)
* Proxying to an external server (e2e TLS, SSH, ...)

### Not working yet:

* Relay TLS certificate verification

See our [Github Issues](https://github.com/pagekite/upagekite/issues/) for
details and a more complete list.


## Bootstrapping Development

Since you are likely to want to iterate on your Python code, a simple
web-based bootstrapping/updating script is included to make life eaiser.

The way it works, is:

1. [bootstrap.py](scripts/bootstrap.py) runs on the ESP32, on startup
2. The script downloads [bootstrap.json](bootstrap.json) from an HTTP server
3. The script downloads all files listed in the "mirror" section,
   saving them to a directory named `bootstrap` on the ESP32.
4. The script runs whatever got installed as `bootstrap/stage_2.py`

(Whether this is (or isn't) a sane way to keep devices in the field up
to date, is left as an exercise for the reader... probably not without
some form of digital signatures! But it's great for development.)


### Bootstrap web server: python3 web server

You can use Python's built-in HTTP server to serve code updates to your
ESP32.

The following commands should be run from within your uPageKite source
folder (the same folder as contains this README.md).

    # Find your machine's current IP address
    ip addr |grep global

    # Or...
    ifconfig |grep netmask

    # Launch the Python server
    python3 -m http.server 8080

In the ESP32 setup below, you will need to set `code_src` to something
like: `http://192.168.1.2:8080/bootstrap.json`

If for some reason your ESP32 is on a different network, or if your IP
address changes frequently enough to be an annoyance, you may prefer to
serve the code over `pagekite.py` instead, as described below.

Otherwise, skip to the ESP32 or localhost setup sections below.


### Bootstrap web server using pagekite.py

You can also use pagekite.py's built-in HTTP server to serve code
updates to your ESP32.

The following commands should be run from within your uPageKite source
folder (the same folder as contains this README.md).

1. Install pagekite.py, see <https://pagekite.net/downloads>
2. Sign up for a [pagekite.net](https://pagekite.net/) account, replace
   USER below with your main kite name.
3. Expose the code folder as https://code-USER.pagekite.me/:

```
pagekite.py . code-USER.pagekite.me
```

Once you have navigated the sign-up, you can configure your bootstrap
(localhost or ESP32) with `code_src` set to:
`https://code-USER.pagekite.me/bootstrap.json`

Now, proceed to the ESP32 or localhost setup sections below.


### Bootstrap setup on the ESP32

After setting up your bootstrap web server (see above), you can follow
the next steps to configure your ESP32 for uPageKite development. All
code-blocks run in the MicroPython REPL:

1. [Install MicroPython on your ESP32](https://docs.micropython.org/en/latest/esp32/tutorial/intro.html).
   The 2020-09-02 v1.13 build is known to work. Connect to the serial
   console and...

2. Set these variables, they will be used in the copy-pastable
   code snippets below:

```
wifi_ssid = "YOUR-SSID"
wifi_key = "YOUR-WIFI-PASSWORD"

code_src = "https://yoursite.com/path/to/bootstrap.json"

kite_name = "DEVICE-USER.pagekite.me"
kite_secret = "SECRET"
```

3. Enable WiFi:

```
import network
wlan = network.WLAN(network.STA_IF)
wlan.active(True)
wlan.connect(wifi_ssid, wifi_key)
```

4. Create a file name `bootstrap-config.json` with your network
   credentials and the URL you want to download code from:

```
import json
with open('bootstrap-config.json', 'w') as fd:
  fd.write(json.dumps(
    {"ssid": wifi_ssid, "key": wifi_key, "src": code_src,
     "kite_name": kite_name, "kite_secret": kite_secret}))
```

5. Configure and enable the web REPL:

```
import webrepl_setup
```

6. [Connect to the Web REPL using a browser](http://micropython.org/webrepl/),
   and upload the file `scripts/bootstrap.py` to the device.

7. Reset the device, to guarantee a clean slate...

8. Run the bootstrap script!

```
execfile('bootstrap.py')
```

That should connect to your wifi and loads the second-stage loader,
running uPageKite and your code. If it works you can press CTRL+C to
return to the Python REPL and proceed...

9. Replace the MicroPython boot script with `bootstrap.py`:

```
os.remove('boot.py')
os.rename('bootstrap.py', 'boot.py')
```

From this point on, you can simply edit the code on your computer and
then reset the device, it will fetch the latest updates on boot.


### Bootstrap setup on localhost

If you want to work on your code locally, without an external device,
uPageKite and the bootstrapping process will run under Python3 or
MicroPython.

1. Edit the bundled [bootstrap-config.json](bootstrap-config.json) file,
   adding `kite_name` and `kite_secret` fields matching your PageKite
   credentials. The contents should look something like this:

```
{
  "kite_name": "device-USER.pagekite.me",
  "kite_secret": "SECRET",
  "src": "http://127.0.0.1:8080/bootstrap.json"
}
```

2. Run the bootstrap script:

```
# With Python3
python3 scripts/bootstrap.py

# Or MicroPython
micropython scripts/bootstrap.py
```


## Copyright and License

**IMPORTANT:**  The upagekite default Free Software license (the GPLv3)
is not suitable for use with most commercial embedded hardware projects,
unless full sources are provided to end-users, along with tools and
documentation necessary for them to make modification and changes.

However, commercial licenses are available for sale for a reasonable
fee. [Get in touch!](https://pagekite.net/support/chat/)

---

Copyright (C) 2020-2021, The Beanstalks Project ehf. and Bjarni R. Einarsson.

This program is free software: you can redistribute it and/or modify it
under the terms of the GNU General Public License as published by the
Free Software Foundation, either version 3 of the License, or (at your
option) any later version.

This program is distributed in the hope that it will be useful, but
WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General
Public License for more details.

You should have received a copy of the GNU General Public License along
with this program. If not, see <https://www.gnu.org/licenses/>.

