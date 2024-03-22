# Experimental mpv IPC socket client based on asyncio

The [mpv media player](https://github.com/mpv-player/mpv) has an [IPC
interface](https://github.com/mpv-player/mpv/blob/master/DOCS/man/ipc.rst)
to control the player from other software. This module is a minimal
client implementation of the low level protocol based on Python
asyncio. It is fully asynchronous, including using the async command
feature of the mpv interface, so commands can be interleaved.

Enjoy! :notes:

## Command-line interface

[`mpvasync.py`](src/mpvasync.py) can be used as a command line tool to:

* Toggle pause status
* Load files to play
* Show the playlist
* Get and set *any* mpv property by name (set only for writable
  properties)
* Monitor mpv events

See `mpvasync.py -h` for details. You can install the package from
source using `pip install .`, which will give you the `mpvasync`
command.

## Python API

The Python API is very limited for now, you pass in command strings
(as defined in the mpv IPC documentation) and possibly arguments, and
get back the data structure returned by mpv, already parsed from
JSON. `mpvasync.MpvError` is raised if a command returns an error.
