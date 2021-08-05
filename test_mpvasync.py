import asyncio
import os
import tempfile
import unittest
import wave
from mpvasync import MpvClient, MpvError
from pathlib import Path


class MpvClientTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # Create a temporary file path for the mpv IPC socket, mpv
        # will replace the file with its socket.
        fh, self.sockpath = tempfile.mkstemp()
        os.close(fh)

    @classmethod
    def setUpClass(cls):
        fh, sample = tempfile.mkstemp()
        os.close(fh)
        # generate wav sample
        with wave.open(sample, 'wb') as w:
            w.setframerate(4)
            w.setsampwidth(4)
            w.setnchannels(1)
            w.writeframes(b'\x00\x00\x00\x00')
        cls.sample = sample

    @classmethod
    def tearDownClass(cls):
        os.unlink(cls.sample)

    async def asyncSetUp(self):
        self.mpv = await asyncio.create_subprocess_exec(
            'mpv', '--idle=yes', f'--input-ipc-server={self.sockpath}',
            '--no-terminal')
        p = Path(self.sockpath)
        # wait for the socket to be ready
        while not p.is_socket():
            await asyncio.sleep(.05)

    async def test_load_file(self):
        async with MpvClient(self.sockpath).connection() as m:
            await m.loadfile(self.sample)
            response = await m.command('get_property', ['playlist'])
            self.assertEqual(response['error'], 'success')
            self.assertEqual(len(response['data']), 1)
            self.assertEqual(response['data'][0]['filename'], self.sample)
            self.assertIsInstance(response['request_id'], int)
            # ensure internal command data has been cleaned up
            self.assertEqual(m._commands, dict())

    async def test_get_playlist(self):
        async with MpvClient(self.sockpath).connection() as m:
            response = await m.command('get_property', ['playlist'])
            self.assertEqual(response['error'], 'success')
            self.assertEqual(response['data'], [])
            self.assertIsInstance(response['request_id'], int)
            # ensure internal command data has been cleaned up
            self.assertEqual(m._commands, dict())

    async def test_invalid_get_command(self):
        async with MpvClient(self.sockpath).connection() as m:
            with self.assertRaises(MpvError):
                # get_property expects only one parameter
                await m.command('get_property', ['playlist', 'xyz'])
            self.assertEqual(m._commands, dict())

    async def test_listen_event(self):
        async with MpvClient(self.sockpath).connection() as m:
            await m.command('observe_property', [1, 'playlist'])

            async def wait_playlist_change():
                async for event in m.listen():
                    if event['event'] == 'property-change' \
                       and event['name'] == 'playlist':
                        return event
            event_wait = asyncio.create_task(wait_playlist_change())

            # make sure the event listener is ready before loading the
            # test file
            while len(m._listeners) < 1:
                await asyncio.sleep(.1)

            await m.loadfile(self.sample)
            event = await event_wait
            self.assertEqual(event['data'][0]['filename'], self.sample)

    async def asyncTearDown(self):
        self.mpv.terminate()
        await self.mpv.wait()

    def tearDown(self):
        os.unlink(self.sockpath)
