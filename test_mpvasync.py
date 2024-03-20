import asyncio
import os
import pytest
import pytest_asyncio
import tempfile
import wave
from mpvasync import MpvClient, MpvError
from pathlib import Path
from typing import Any


@pytest.fixture
def sockpath():
    fh, s = tempfile.mkstemp()
    os.close(fh)
    yield s
    os.unlink(s)


@pytest.fixture(scope='module')
def sample():
    fh, sample = tempfile.mkstemp()
    os.close(fh)
    # generate wav sample
    with wave.open(sample, 'wb') as w:
        w.setframerate(4)
        w.setsampwidth(4)
        w.setnchannels(1)
        w.writeframes(b'\x00\x00\x00\x00')
    yield sample
    os.unlink(sample)


@pytest_asyncio.fixture
async def mpv_sock(sockpath):
    mpv = await asyncio.create_subprocess_exec(
        'mpv', '--ao=null', '--idle=yes',
        f'--input-ipc-server={sockpath}',
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    p = Path(sockpath)
    # wait for the socket to be ready
    while not p.is_socket():
        await asyncio.sleep(.05)
    yield sockpath
    mpv.terminate()
    stdout, stderr = await mpv.communicate()
    print(stdout.decode())
    print(stderr.decode())


async def test_load_file(mpv_sock, sample):
    async with MpvClient(mpv_sock).connection() as m:
        await m.loadfile(sample)
        response = await m.command('get_property', ['playlist'])
        assert response['error'] == 'success'
        assert len(response['data']) == 1
        assert response['data'][0]['filename'] == sample
        assert isinstance(response['request_id'], int)
        # ensure internal command data has been cleaned up
        assert len(m._commands) == 0


async def test_get_playlist(mpv_sock):
    async with MpvClient(mpv_sock).connection() as m:
        response = await m.command('get_property', ['playlist'])
        assert response['error'] == 'success'
        assert response['data'] == []
        assert isinstance(response['request_id'], int)
        # ensure internal command data has been cleaned up
        assert len(m._commands) == 0


async def test_invalid_get_command(mpv_sock):
    async with MpvClient(mpv_sock).connection() as m:
        with pytest.raises(MpvError):
            # get_property expects only one parameter
            await m.command('get_property', ['playlist', 'xyz'])
        assert len(m._commands) == 0


async def test_listen_event(mpv_sock, sample):
    async with MpvClient(mpv_sock).connection() as m:
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

        await m.loadfile(sample)
        events = await event_wait
        for event in events:
            # sometimes there's an initial event with empty
            # playlist before the test file is loaded
            if len(event['data']) == 0:
                continue
            assert event['data'][0]['filename'] == sample
