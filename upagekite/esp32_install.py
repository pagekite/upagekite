"""\
Emits a script to reconfigure and upload code to Micropython running on
an ESP32 (or Raspberry Pi Pico W), over the serial link. The output of this
script is timed and is meant to be piped into a picocom instance, which
handles connecting to the Micropython serial console.

Usage:
    python3 -m upagekite.esp32_install [options] \\
        | picocom --lower-dtr --lower-rts -b115200 /dev/ttyUSB0

(Note that the --lower-dtr and/or --lower-rts arguments to picocom may
 not be necessary (or may even cause problems) for your device. Those
 work with the ESP32-CAM modules at least!)

Options:
    --clean      Clean previous install
    --app        Only update files from $UPK_APP (default: webapp/)
    --upagekite  Only update files in upagekite/
    --all        Update all source files
    --changed    Skip updates if file is unchanged since last time

    --reset      Remove app settings (bootstrap-config.json)
    --config     Configure WiFi and/or PageKite settings (see below)

    --onboot     Make the app start automatically on boot
    --launch     Launch the app when the script completes

    --nopk       Equivalent to: --app --changed --config --launch

If no options are provided, runs: "--all --changed --config --launch"

The --config option will search the environment for these variables, and
use them to configure the device if they are present:

    UPK_WIFI_SSID
    UPK_WIFI_KEY
    UPK_KITE_NAME
    UPK_KITE_SECRET

The environment variable UPK_APP, if set, is the path to the webapp
you would like installed.
"""
import os
import sys
import time
import datetime


BASEDIR = os.path.normpath(os.path.join(os.path.dirname(__file__), '..'))
BOOTSTRAP = os.path.join(BASEDIR, 'upagekite', 'esp32_bootstrap.py')
CHANGE_MARKER = '/tmp/upk-change-marker.%d' % os.getuid()

CTRL_C = chr(ord('C') & 31)
CTRL_D = chr(ord('D') & 31)
CTRL_E = chr(ord('E') & 31)


try:
    CHANGE_LAST = os.stat(CHANGE_MARKER).st_mtime
except:
    CHANGE_LAST = 0


def _s(delay, message=None, eol=b'\r\n'):
    if message is not None:
        m = bytes(message.rstrip(), 'utf-8') if isinstance(message, str) else message
        sys.stdout.buffer.write(m + eol)
        sys.stdout.buffer.flush()
    time.sleep(delay)


def _send_escaped(lines):
    count = 0
    for line in lines:
        count += 1
        _s(0.001 + len(line) / 10000.0,
            line.replace('\\', '\\\\').replace('"', '\\"'), eol=b'\n')
    return count


def _send_lines(lines):
    count = 0
    for line in lines:
        count += 1
        _s(0.02, line or '')
    return count


def _send_file(filename, target=None):
    _s(0.1, CTRL_E)
    _s(0.1, 'filedata = """\\')
    count = _send_escaped(open(filename, 'r'))
    _s(0.1, '"""')
    _send_lines(("""\
target = open("%s", "w")
target.write(filedata)
target.close()
""" % (target or os.path.basename(filename))).splitlines())
    _s(0.1, CTRL_D)
    _s(1 + count / 500.0)


def _dir_to_upload_list(source_base, target_base):
    upload_list = [(source_base, target_base)]
    for dn in os.listdir(source_base):
        dpath = os.path.join(source_base, dn)
        if (dn[:1] != '.' and dn not in ('build', 'dist', '__pycache__')
                and os.path.isdir(dpath)):
            upload_list += _dir_to_upload_list(dpath, target_base + '/' + dn)
    return upload_list


def emit_script(argv):
    if not argv:
        argv = ['--all', '--changed', '--config', '--launch']
    if '--nopk' in argv:
        argv.remove('--nopk')
        argv.extend(['--app', '--changed', '--config', '--launch'])

    def changed(fn):
        try:
            return (os.stat(fn).st_mtime >= CHANGE_LAST)
        except:
            return True
    if '--changed' not in argv:
        changed = lambda f: True

    _s(2, CTRL_C)
    _s(2, CTRL_C)
    _s(1, CTRL_C)
    _s(0.1, '### Preparing to upload requested files... ###')
    _s(0.1, 'from machine import RTC')
    _s(0.1, 'RTC().datetime(%s)' % (datetime.datetime.now().utctimetuple()[:-1],))

    _s(0.1, 'import os')
    _s(0.1, 'import utime as time')

    if changed(BOOTSTRAP) or '--clean' in argv:
        _send_file(BOOTSTRAP, 'bootstrap.py')
    _s(0.1, 'from bootstrap import rm_rf, mkdirexist')

    if '--clean' in argv:
        _s(0.1, 'rm_rf("bootstrap_live")')
        if os.path.exists(CHANGE_MARKER):
            os.remove(CHANGE_MARKER)
    _s(0.1, 'mkdirexist("bootstrap_live")')
    _s(2)

    SKIPPING = ['.', '..', 'esp32_bootstrap.py', 'esp32_install.py']
    UPLOADING = []

    if '--app' in argv or '--all' in argv:
        j = os.path.join
        app_dir = os.getenv('UPK_APP') or os.path.join(BASEDIR, 'webapp')
        UPLOADING.extend(_dir_to_upload_list(app_dir, 'bootstrap_live'))

    if '--upagekite' in argv or '--all' in argv:
        UPLOADING.extend(_dir_to_upload_list(
            os.path.join(BASEDIR, 'upagekite'),
            'bootstrap_live/upagekite'))

    for subdir, destdir in UPLOADING:
        _s(0.1, 'mkdirexist("%s")' % destdir)
        for fn in os.listdir(subdir):
            if (fn not in SKIPPING
                    and fn.rsplit('.', 1)[-1] in ('py', 'css', 'html')):
                fpath = os.path.join(subdir, fn)
                if os.path.isfile(fpath) and changed(fpath):
                    _send_file(fpath, '%s/%s' % (destdir, fn))

    if UPLOADING:
        open(CHANGE_MARKER, 'w+').close()

    if '--reset' in argv:
        _s(1, 'rm_rf("bootstrap-config.json")')

    if '--config' in argv:
        _s(0.1, 'from bootstrap import setting')
        for setting, envvar in (
                ('kite_name',   'UPK_KITE_NAME'),
                ('kite_secret', 'UPK_KITE_SECRET'),
                ('ssid',        'UPK_WIFI_SSID'),
                ('key',         'UPK_WIFI_KEY')):
            if os.getenv(envvar):
                _s(0.1, 'setting("%s", "%s") and None' % (setting, os.getenv(envvar)))

    if '--onboot' in argv:
        _s(0.1, 'fd = open("boot.py", "w")')
        _s(0.1, 'fd.write("execfile(\\"bootstrap.py\\")")')
        _s(0.1, 'fd.close()')

    if '--launch' in argv:
        _s(1, 'execfile("bootstrap.py")')
    else:
        _s(0.1, 'from bootstrap import bootstrap_1, load_settings')
        _s(0.1, 'bootstrap_1(load_settings(), download=False)')
        _s(1, '### Uploads done, you can play with the REPL now. CTRL-D quits! ###')


if __name__ == '__main__':
    emit_script(sys.argv[1:])
    for line in sys.stdin:
        _s(0, line)

