# upagekite: MicroPython/ESP32 PageKite web server

This code makes it very easy to create static web sites or simple web
services in MicroPython, and automatically punch through firewalls and
NAT to make the server reachable from the wider Internet.

This is a minimal HTTP server, web micro-framework and PageKite
implementation, written for use with MicroPython on the ESP32. It is also
tested on Ubuntu/Python 3.7 and Ubuntu's MicroPython snap. You will need
access to a PageKite relay, such as those provided by
[pagekite.net](https://pagekite.net/).


**WARNING:** This code does not magically make the ESP32 suitable for
hosting a high-volume webapp. Not does it "solve" security. Be careful!


## Hacking uHowTo

1. Clone upagekite: `git clone https://github.com/pagekite/upagekite/`
2. Follow the **Bootstrapping Development** guide below
3. Make changes to [stage_2.py](webapp/stage_2.py),
   the [webapp](webapp/webroot/),
   or [upagekite](upagekite/) itself.
4. Iterate!

Consult [webapp/README.md](webapp/README.md) for guidance on how to
develop simple web apps or APIs using this framework.

Alternately, you may be better off exploring
[the Tutorial](https://github.com/pagekite/upagekite-tutorial/`).


## Project Status

### Works:

* Exposing a hello-world webapp via. [pagekite.net](https://pagekite.net/)
* Network-based bootstrapping, load & run code from the web
* Tested platforms and pythons:
   * MicroPython 1.14 on an ESP32-WROOM-32 DevKitC board
   * MicroPython 1.14 on Ubuntu Linux
   * Python 3.8.10 on Ubuntu Linux
* Adaptive relay selection (ESP32 relies on DNS hints from web)
* Proxying to an external server (e2e TLS, SSH, ...)

### Not working yet:

* Relay TLS certificate verification

See our [Github Issues](https://github.com/pagekite/upagekite/issues/) for
details and a more complete list.


## Bootstrapping Development

**Note:** Before you start, you may want to sign up for a
[pagekite.net](https://pagekite.net/) account.


### Local Python 3.x development

Take a look at the [hello.py](scripts/hello.py) sample script.

You can probably just run it:

    cd /path/to/upagekite
    python3 scripts/hello.py myname.pagekite.me mysecret

Since the sample app is written with the ESP32 in mind, some things may
not work. You can port over code from [webapp/stage_2.py](stage_2.py) into
[hello.py](scripts/hello.py) for fun and profit.


### Running on a live ESP32

There are many ways to upload code to your ESP32. Here we will describe
only one; using `picocom` to manage the serial link, and
`upagekite.esp32_install` to drive it.

**1. Verify that Linux sees your ESP32 as a serial device**

    $ dmesg |grep -i usb |tail -5
    [...] usb 3-1: new full-speed USB device number 57 using xhci_hcd
    [...] usb 3-1: New USB device found, idVendor=1a86, idProduct=7523, ...
    [...] usb 3-1: New USB device strings: Mfr=0, Product=2, SerialNumber=0
    [...] usb 3-1: Product: USB2.0-Ser!
    [...] usb 3-1: ch341-uart converter now attached to ttyUSB0

In this example, the ESP32 is connected to `/dev/ttyUSB0`.

**2. Make sure you can talk to Micropython**

If you haven't already flashed your
[ESP32 with Micropython](https://docs.micropython.org/en/latest/esp32/tutorial/intro.html),

    $ picocom -b115200 --lower-dtr --lower-rts /dev/ttyUSB0
    ...
    MicroPython v1.14-122-g9fef1c0bd-dirty [...] with ESP32
    Type "help()" for more information.
    >>>

(You may want to experiment with omit the `--lower-dtr` and `--lower-rts`
arguments above; some boards need them, some don't. Skipping them is
preferable, since they reboot the board every time, but I haven't found
any other reliable way to connect to the ESP32-CAM.)
    
**3. Configure and upload code to the device**

If you know your WiFi details and PageKite credentials, you may want to
set some enviroment variables first:

    $ export UPK_WIFI_SSID="yourwifi"
    $ export UPK_WIFI_KEY="wifiKey"
    $ export UPK_KITE_NAME="yourkitename.pagekite.me"
    $ export UPK_KITE_SECRET="verySecretSecret"

(If you skip the above step, the default sample app should enable a captive
portal on the ESP32 which will let you input settings interactively, which
can be fun.)

    $ python3 -m upagekite.esp32_install \
       |picocom -b115200 --lower-dtr --lower-rts /dev/ttyUSB0

    [... lots of output omitted ...]

Without any arguments, this will upload all of `upagekite` and all of
the sample app to the board's flash, in a folder named `bootstrap_live`.

The app should then run!

By default, the install helper scans the `upagekite/` and `webapp/`
folders for changed files and uploads anything new, configurs WiFi and
pagekite credentials and launches the app. But it can do other things
too, see `pydoc3 upagekite.esp32_install` for details. 


**4. Commence hacking!**

At this point, you will hopefully have made contact with your ESP32 and
launched a live webapp.

You can either hack on the sample app until it does what you want, or
explore [the Tutorial](https://github.com/pagekite/upagekite-tutorial/`)
for a more structured approach.

Note that uploading Python code to the flash and compiling it on the
chip as described above, is quite inefficient use of precious RAM.  Once
you have an idea what you want to develop, you will probably want to
build your own custom Micropython firmware and "freeze" your Python code
into the binary. This allows Micropython to run the bytecode directly
from FLASH and conserve RAM for use by your application.


## Copyright and License

**IMPORTANT:**  The upagekite default Free Software license (the GPLv3)
is not suitable for use with most commercial embedded hardware projects,
unless full sources are provided to end-users, along with tools and
documentation necessary for them to make modification and changes.

However, commercial licenses are available for sale for a reasonable
fee. [Get in touch!](https://pagekite.net/support/chat/)

---

Copyright (C) 2020-2022, The Beanstalks Project ehf. and Bjarni R. Einarsson.

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

