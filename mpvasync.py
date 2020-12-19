#!/usr/bin/python3
# PYTHON_ARGCOMPLETE_OK
import asyncio
import json
import logging
import sys
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)


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
        return response

    @asynccontextmanager
    async def connection(self):
        try:
            await self.connect()
            yield self
        finally:
            await self.close()


async def toggle_pause(args):
    async with MpvClient(args.socket).connection() as m:
        response = await m.command('cycle', ['pause'])
        if response['error'] != 'success':
            print(f'Command failed: {response!s}', file=sys.stderr)
            return 1


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(
        description='Toggle mpv pause')
    parser.add_argument('--socket', default='/tmp/mpvsocket',
                        help='mpv JSON IPC socket to connect to')
    parser.add_argument('--log', default='INFO',
                        choices={'CRITICAL', 'ERROR', 'WARNING',
                                 'INFO', 'DEBUG'},
                        help='mpv JSON IPC socket to connect to')
    subparsers = parser.add_subparsers(title='commands')
    pause = subparsers.add_parser('toggle-pause', aliases=['toggle'])
    pause.set_defaults(func=toggle_pause)

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
        ret = asyncio.run(args.func(args))
        sys.exit(ret)
