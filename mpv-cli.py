#!/usr/bin/python3
import asyncio
import json
from contextlib import asynccontextmanager


class MpvCli:
    def __init__(self, path):
        self.path = path

    async def connect(self):
        self.reader, self.writer = \
            await asyncio.open_unix_connection(self.path)

    async def close(self):
        self.writer.close()
        await self.writer.wait_closed()

    async def command(self, cmd):
        self.writer.write(json.dumps(cmd, separators=(',', ':')).encode())
        self.writer.write(b'\n')
        await self.writer.drain()

        response = json.loads((await self.reader.readline()).decode())
        return response

    @asynccontextmanager
    async def connection(self):
        try:
            await self.connect()
            yield self
        finally:
            await self.close()


async def main():
    async with MpvCli('/tmp/mpvsock').connection() as m:
        pause_command = {'command': ['get_property', 'pause']}
        response = await m.command(pause_command)
        print(response)

        toggle_command = {'command': ['set_property', 'pause',
                                      not response['data']]}
        response = await m.command(toggle_command)
        print(response)


if __name__ == '__main__':
    asyncio.run(main())
