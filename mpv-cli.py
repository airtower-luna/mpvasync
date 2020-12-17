#!/usr/bin/python3
import asyncio
import json
from contextlib import asynccontextmanager


class MpvClient:
    def __init__(self, path):
        self.path = path
        self._commands = dict()
        self._commands_lock = asyncio.Lock()
        self._cid = 1

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
                print(f'Received event: {msg!s}')

    async def close(self):
        self.writer.close()
        await self.writer.wait_closed()
        await self._handler

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


async def main():
    async with MpvClient('/tmp/mpvsock').connection() as m:
        response = await m.command('get_property', ['pause'])
        print(response)

        response = await m.command('set_property',
                                   ['pause', not response['data']])
        print(response)


if __name__ == '__main__':
    asyncio.run(main())
