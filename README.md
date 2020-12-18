# Experimental mpv IPC socket client based on asyncio

The [mpv media player](https://github.com/mpv-player/mpv) has an [IPC
interface](https://github.com/mpv-player/mpv/blob/master/DOCS/man/ipc.rst)
to control the player from other software. This module is a minimal
client implementation of the low level protocol based on Python
asyncio. It is fully asynchronous, including using the async command
feature of the mpv interface, so commands can be interleaved.

The Python API is very limited for now, you pass in command strings
(as defined in the mpv IPC documentation) and possibly arguments, and
get back the data structure returned by mpv, already parsed from JSON.

If you run [`mpvasync.py`](mpvasync.py) as a script it will toggle the
pause status.

Enjoy! :notes:
