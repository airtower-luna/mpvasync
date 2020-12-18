import asyncio
import os
import tempfile
import unittest
from mpvasync import MpvClient
from pathlib import Path


class MpvClientTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # Create a temporary file path for the mpv IPC socket, mpv
        # will replace the file with its socket.
        fh, self.sockpath = tempfile.mkstemp()
        os.close(fh)

    async def asyncSetUp(self):
        self.mpv = await asyncio.create_subprocess_exec(
            'mpv', '--idle=yes', f'--input-ipc-server={self.sockpath}',
            '--no-terminal')
        p = Path(self.sockpath)
        # wait for the socket to be ready
        while not p.is_socket():
            await asyncio.sleep(.05)

    async def test_get_playlist(self):
        async with MpvClient(self.sockpath).connection() as m:
            response = await m.command('get_property', ['playlist'])
            self.assertEqual(response['error'], 'success')
            self.assertEqual(response['data'], [])
            self.assertIsInstance(response['request_id'], int)
            # ensure internal command data has been cleaned up
            self.assertEqual(m._commands, dict())

    async def asyncTearDown(self):
        self.mpv.terminate()
        await self.mpv.wait()

    def tearDown(self):
        os.unlink(self.sockpath)
