#!/usr/bin/python3
# PYTHON_ARGCOMPLETE_OK
import asyncio
import json
import logging
from contextlib import asynccontextmanager
from typing import Any, Dict, AsyncIterable, Mapping, Optional, Sequence, Set

logger = logging.getLogger(__name__)


class MpvError(Exception):
    '''This exception is raised if mpv returns an error for a command.'''
    def __init__(self, response: Mapping[str, Any]) -> None:
        super().__init__(response['error'])


class MpvCommandState():
    '''Stored in the client's _commands dict before sending an async
    command to mpv. The event is set after a response has been
    received and written to the response attribute.

    '''
    def __init__(self) -> None:
        self.event = asyncio.Event()
        self.response: Optional[Dict[str, Any]] = None


class MpvClient:
    def __init__(self, path: str) -> None:
        self.path = path
        self._commands: Dict[int, MpvCommandState] = dict()
        self._commands_lock = asyncio.Lock()
        self._listeners: Set[asyncio.Queue] = set()
        self._listeners_lock = asyncio.Lock()
        self._cid = 1
        self.writer: Optional[asyncio.StreamWriter] = None

    async def connect(self) -> None:
        self.reader, self.writer = \
            await asyncio.open_unix_connection(self.path)
        self._handler = asyncio.create_task(self._handle_incoming())

    async def _handle_incoming(self) -> None:
        while (raw := await self.reader.readline()) != b'':
            msg = json.loads(raw.decode())
            if cid := msg.get('request_id'):
                async with self._commands_lock:
                    self._commands[cid].response = msg
                    self._commands[cid].event.set()
            else:
                logging.debug(f'Received event: {msg!s}')
                async with self._listeners_lock:
                    for listener in self._listeners:
                        await listener.put(msg)

        async with self._listeners_lock:
            for listener in self._listeners:
                await listener.put(None)

    async def close(self) -> None:
        if self.writer is not None:
            self.writer.close()
            await self.writer.wait_closed()
            await self._handler
            self.writer = None

    async def listen(self) -> AsyncIterable[Dict]:
        q: asyncio.Queue[Dict] = asyncio.Queue()
        async with self._listeners_lock:
            self._listeners.add(q)
        try:
            while True:
                event = await q.get()
                if event is None:
                    break
                else:
                    yield event
        finally:
            async with self._listeners_lock:
                self._listeners.remove(q)

    async def command(self, cmd: str, params: Sequence[str] = []) \
            -> Dict[str, Any]:
        if self.writer is None:
            raise ValueError('Not connected to mpv!')

        async with self._commands_lock:
            cid = self._cid
            # Let's assume there will be sufficiently fewer than 65536
            # requests active at any point in time. Note that the
            # request ID for async requests MUST NOT be 0 or they will
            # hang indefinitely.
            self._cid = self._cid % 65536 + 1
            self._commands[cid] = MpvCommandState()

        self.writer.write(json.dumps(
            {'command': [cmd, *params], 'request_id': cid, 'async': True},
            separators=(',', ':')).encode())
        self.writer.write(b'\n')
        await self.writer.drain()

        await self._commands[cid].event.wait()
        async with self._commands_lock:
            response = self._commands[cid].response
            assert response is not None
            del self._commands[cid]
        logging.debug(f'Received response: {response!s}')

        if response['error'] != 'success':
            raise MpvError(response)
        return response

    async def loadfile(self, file: str, append: bool = False):
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
            await m.loadfile(f, append=(args.append or i > 0))


async def toggle_pause(args):
    async with MpvClient(args.socket).connection() as m:
        await m.command('cycle', ['pause'])


async def monitor(args):
    async with MpvClient(args.socket).connection() as m:
        for i, p in enumerate(args.properties, start=1):
            await m.command('observe_property', [i, p])
        async for event in m.listen():
            print(f'Received {event["event"]} event: {event!s}')

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
    mon = subparsers.add_parser('monitor', help='monitor mpv events')
    mon.set_defaults(func=monitor)
    mon.add_argument('--property', '-p', action='append', dest='properties',
                     metavar='PROPERTY', default=[],
                     help='monitor this property (may be specified multiple '
                     'times)')

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
        try:
            asyncio.run(args.func(args))
        except KeyboardInterrupt:
            logging.info('Received keyboard interrupt, exiting.')
