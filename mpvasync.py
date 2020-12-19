#!/usr/bin/python3
# PYTHON_ARGCOMPLETE_OK
import asyncio
import json
import logging
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)


class MpvError(Exception):
    '''This exception is raised if mpv returns an error for a command.'''
    def __init__(self, response):
        super().__init__(response['error'])


class MpvClient:
    def __init__(self, path):
        self.path = path
        self._commands = dict()
        self._commands_lock = asyncio.Lock()
        self._cid = 1
        self.writer = None

    async def connect(self):
        self.reader, self.writer = \
            await asyncio.open_unix_connection(self.path)
        self._handler = asyncio.create_task(self._handle_incoming())

    async def _handle_incoming(self):
        while (raw := await self.reader.readline()) != b'':
            msg = json.loads(raw.decode())
            if cid := msg.get('request_id'):
                async with self._commands_lock:
                    event = self._commands[cid]
                    self._commands[cid] = msg
                    event.set()
            else:
                logging.info(f'Received event: {msg!s}')

    async def close(self):
        if self.writer is not None:
            self.writer.close()
            await self.writer.wait_closed()
            await self._handler
            self.writer = None

    async def command(self, cmd, params=[]):
        async with self._commands_lock:
            cid = self._cid
            # Let's assume there will be sufficiently fewer than 65536
            # requests active at any point in time. Note that the
            # request ID for async requests MUST NOT be 0 or they will
            # hang indefinitely.
            self._cid = self._cid % 65536 + 1
            event = asyncio.Event()
            self._commands[cid] = event

        self.writer.write(json.dumps(
            {'command': [cmd, *params], 'request_id': cid, 'async': True},
            separators=(',', ':')).encode())
        self.writer.write(b'\n')
        await self.writer.drain()

        await event.wait()
        async with self._commands_lock:
            response = self._commands[cid]
            del self._commands[cid]
        logging.debug(f'Received response: {response!s}')

        if response['error'] != 'success':
            raise MpvError(response)
        return response

    async def loadfile(self, file, append=False):
        args = [file]
        if append:
            args.append('append')
        return await self.command('loadfile', args)

    @asynccontextmanager
    async def connection(self):
        try:
            await self.connect()
            yield self
        finally:
            await self.close()


async def playlist(args):
    async with MpvClient(args.socket).connection() as m:
        response = await m.command('get_property', ['playlist'])
        for p in response['data']:
            print(f'{"*" if p.get("current") else " "} {p["filename"]}')


async def load_file(args):
    async with MpvClient(args.socket).connection() as m:
        for i, f in enumerate(args.file):
            response = await m.loadfile(f, append=(args.append or i > 0))


async def toggle_pause(args):
    async with MpvClient(args.socket).connection() as m:
        await m.command('cycle', ['pause'])


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(
        description='control mpv via socket IPC')
    parser.add_argument(
        '--socket', default='/tmp/mpvsocket',
        help='mpv JSON IPC socket to connect to')
    parser.add_argument(
        '--log', default='INFO', help='mpv JSON IPC socket to connect to',
        choices={'CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG'})
    subparsers = parser.add_subparsers(title='commands')
    pause = subparsers.add_parser(
        'toggle-pause', aliases=['toggle'], help='toggle pause/play')
    pause.set_defaults(func=toggle_pause)
    load = subparsers.add_parser(
        'loadfile', help='load files (or URLs) to play')
    load.set_defaults(func=load_file)
    load.add_argument('file', nargs='+', help='files (or URLs) to play')
    load.add_argument(
        '--append', '-a', action='store_true',
        help='append file(s) to current playlist instead of replacing it')
    plist = subparsers.add_parser('playlist', help='show current playlist')
    plist.set_defaults(func=playlist)

    # enable bash completion if argcomplete is available
    try:
        import argcomplete
        argcomplete.autocomplete(parser)
    except ImportError:
        pass

    args = parser.parse_args()
    logging.basicConfig(level=getattr(logging, args.log))
    if 'func' not in args:
        parser.print_usage()
    else:
        asyncio.run(args.func(args))
