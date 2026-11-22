"""An event loop on a clock of its own, for tests of timing (stream pacing,
waits before a decision): when nothing is ready it moves its time on to the
next timer at once instead of waiting for it. The code under test runs as on
the real clock, only exactly (no late timers, no render time) and without
waiting: the tests' seconds of sleeps take no time.

    run_on_virtual_clock(scenario())

While it runs, time.monotonic() is that clock too (the code's stamps and
windows, like the light's echo windows), so both clocks agree. It starts at
the real time.monotonic(): stamps left at their defaults are as old as they
are on the real clock. A task waiting for a thread or a socket would see time
jump ahead: only for code that waits on timers and on itself."""

import asyncio
import time
import unittest.mock


class VirtualClockLoop(asyncio.SelectorEventLoop):
    def __init__(self):
        self._now = time.monotonic()
        super().__init__()
        self._clock_resolution = 1e-9  # a timer runs at its time, not up to 15 ms early
        select = self._selector.select

        def advancing(timeout=None):
            if timeout is None or timeout <= 0:
                return select(timeout)
            events = select(0)
            if not events:
                self._now += timeout
            return events

        self._selector.select = advancing

    def time(self):
        return self._now


def run_on_virtual_clock(coro):
    """``coro`` run to its end on a VirtualClockLoop, time.monotonic() on
    its clock meanwhile."""
    with asyncio.Runner(loop_factory=VirtualClockLoop) as runner:
        loop = runner.get_loop()
        with unittest.mock.patch.object(time, "monotonic", loop.time):
            return runner.run(coro)
