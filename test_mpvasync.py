import asyncio
import os
import tempfile
import unittest
import wave
from mpvasync import MpvClient, MpvError
from pathlib import Path
from typing import Any


class MpvClientTest(unittest.IsolatedAsyncioTestCase):
    sample: str

    def setUp(self) -> None:
        # Create a temporary file path for the mpv IPC socket, mpv
        # will replace the file with its socket.
        fh, self.sockpath = tempfile.mkstemp()
        os.close(fh)

    @classmethod
    def setUpClass(cls) -> None:
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
    def tearDownClass(cls) -> None:
        os.unlink(cls.sample)

    async def asyncSetUp(self) -> None:
        self.mpv = await asyncio.create_subprocess_exec(
            'mpv', '--ao=null', '--idle=yes',
            f'--input-ipc-server={self.sockpath}',
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        p = Path(self.sockpath)
        # wait for the socket to be ready
        while not p.is_socket():
            await asyncio.sleep(.05)

    async def test_load_file(self) -> None:
        async with MpvClient(self.sockpath).connection() as m:
            await m.loadfile(self.sample)
            response = await m.command('get_property', ['playlist'])
            self.assertEqual(response['error'], 'success')
            self.assertEqual(len(response['data']), 1)
            self.assertEqual(response['data'][0]['filename'], self.sample)
            self.assertIsInstance(response['request_id'], int)
            # ensure internal command data has been cleaned up
            self.assertEqual(m._commands, dict())

    async def test_get_playlist(self) -> None:
        async with MpvClient(self.sockpath).connection() as m:
            response = await m.command('get_property', ['playlist'])
            self.assertEqual(response['error'], 'success')
            self.assertEqual(response['data'], [])
            self.assertIsInstance(response['request_id'], int)
            # ensure internal command data has been cleaned up
            self.assertEqual(m._commands, dict())

    async def test_invalid_get_command(self) -> None:
        async with MpvClient(self.sockpath).connection() as m:
            with self.assertRaises(MpvError):
                # get_property expects only one parameter
                await m.command('get_property', ['playlist', 'xyz'])
            self.assertEqual(m._commands, dict())

    async def test_listen_event(self) -> None:
        async with MpvClient(self.sockpath).connection() as m:
            await m.command('observe_property', [1, 'playlist'])

            async def wait_playlist_change() -> list[dict[str, Any]]:
                events = list()
                async for event in m.listen():
                    if event['event'] == 'property-change' \
                       and event['name'] == 'playlist':
                        events.append(event)
                    elif event['event'] == 'idle':
                        break
                return events
            event_wait = asyncio.create_task(wait_playlist_change())

            # make sure the event listener is ready before loading the
            # test file
            step = 0.1
            waited = 0.0
            while waited < 5:
                async with m._listeners_lock:
                    if len(m._listeners) > 0:
                        break
                await asyncio.sleep(step)
                waited += step

            await m.loadfile(self.sample)
            events = await event_wait
            for event in events:
                # sometimes there's an initial event with empty
                # playlist before the test file is loaded
                if len(event['data']) == 0:
                    continue
                self.assertEqual(event['data'][0]['filename'], self.sample)

    async def asyncTearDown(self) -> None:
        self.mpv.terminate()
        stdout, stderr = await self.mpv.communicate()
        print(stdout.decode())
        print(stderr.decode())

    def tearDown(self) -> None:
        os.unlink(self.sockpath)
