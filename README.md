# upagekite: MicroPython PageKite connector (for the ESP32)

**WARNING:** This is ALPHA QUALITY CODE. Get in touch and have a chat
             before using it for anything important! Here be dragons!

This code makes it very easy to create simple web services in
MicroPython and make them reachable from the wider Internet.

This is a minimal PageKite implementation written for use with
MicroPython on the ESP32. It is also tested on Ubuntu/Python 3.7 and
Ubuntu's MicroPython snap.

You will need a [pagekite.net](https://pagekite.net/) account or your
own PageKite relay.

**WARNING:** This code does not magically make the ESP32 suitable for
hosting a high-volume website. Not does it "solve" security. Be careful!


## Hacking uHowTo

1. Clone this repo: `git clone https://github.com/pagekite/upagekite/'
2. Follow the **Bootstrapping Development** guide below
3. Make your changes to [bootstrap_2.py](scripts/bootstrap_2.py)
4. Add new code files to "mirror" in [bootstrap.json](bootstrap.json)
5. Iterate!


## Project Status

### Works:

* Exposing a hello-world website via. pagekite.net
* Network-based bootstrapping, load & run code from the web
* Tested platforms and pythons:
   * MicroPython 1.13 on an ESP32-WROOM-32 DevKitC board
   * MicroPython 1.13 on Ubuntu Linux
   * Python 3.7.5 on Ubuntu Linux

### Not working yet:

* Dynamic DNS updates
* Relay TLS certificate verification
* Adaptive relay selection (ESP32 DNS lookups are too limited)
* Large HTTP POST requests or file uploads
* Proxying to an external (web)server


## Bootstrapping Development

Since you are likely to want to iterate on your Python code, a simple
web-based bootstrapping/updating script is included to make life eaiser.

The way it works, is:

1. [bootstrap.py](scripts/bootstrap.py) runs on the ESP32, on startup
2. The script downloads [bootstrap.json](bootstrap.json)
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

Otherwise, skip to the ESP32 setup section.


### Bootstrap web server using pagekite.py

You can also use pagekite.py's built-in HTTP server to serve code
updates to your ESP32.

The following commands should be run from within your uPageKite source
folder (the same folder as contains this README.md).

1. Install pagekite.py, see <https://pagekite.net/downloads>
2. Sign up for a [pagekite.net](https://pagekite.net/) account, replace
   USER below with your main kite name.
3. Expose the code folder as https://code-USER.pagekite.me/:

    pagekite.py . code-USER.pagekite.me

Once you have navigated the sign-up, you can configure your ESP32
bootstrap with `code_src` set to:
`https://code-USER.pagekite.me/bootstrap.json`


### Bootstrap setup on the ESP32

Follow these steps to configure your ESP32 for uPageKite development
(all code-blocks run in the MicroPython REPL):

1. [Install MicroPython on your ESP32](https://docs.micropython.org/en/latest/esp32/tutorial/intro.html).
   The 2020-09-02 v1.13 build is known to work. Connect to the serial
   console and...

2. Set these variables, they will be used in the copy-pastable
   code snippets below:

    wifi_ssid = "YOUR-SSID"
    wifi_key = "YOUR-WIFI-PASSWORD"

    code_src = "https://yoursite.com/path/to/bootstrap.json"

    kite_name = "DEVICE-USER.pagekite.me"
    kite_secret = "SECRET"

3. Enable WiFi:

    import network
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(wifi_ssid, wifi_key)

4. Create a file name `bootstrap-config.json` with your network
   credentials and the URL you want to download code from:

    import json
    with open('bootstrap-config.json', 'w') as fd:
      fd.write(json.dumps(
        {"ssid": wifi_ssid, "key": wifi_key, "src": code_src,
         "kite_name": kite_name, "kite_secret": kite_secret}))

5. Configure and enable the web REPL:

    import webrepl_setup

6. [Connect to the Web REPL using a browser](http://micropython.org/webrepl/),
   and upload the file `scripts/bootstrap.py` to the device.

7. Reset the device, to guarantee a clean slate...

8. Run the bootstrap script!

    execfile('bootstrap.py')

9. If that successfully connects to your wifi and loads the
   second-stage loader, make it permanent with:

    os.remove('boot.py')
    os.rename('bootstrap.py', 'boot.py')

From this point on, you can simply edit the code on your computer and
then reset the device, it will fetch the latest updates on boot.


## Copyright and License

Copyright (C) 2020, The Beanstalks Project ehf. and Bjarni R. Einarsson.

This program is free software: you can redistribute it and/or modify it
under the terms of the GNU Lesser General Public License as published by
the Free Software Foundation, either version 3 of the License, or (at
your option) any later version.

This program is distributed in the hope that it will be useful, but
WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU Lesser
General Public License for more details.

You should have received a copy of the GNU Lesser General Public License
along with this program. If not, see <https://www.gnu.org/licenses/>.

