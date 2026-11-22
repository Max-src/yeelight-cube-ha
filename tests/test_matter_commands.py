"""Yeelight writes and commands over Matter (matter_commands.py): which
server delivers them, and nothing breaks when none does."""

import asyncio
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
from ha_stubs import import_pure_module  # noqa: E402

COMMANDS = import_pure_module("matter_commands")

REFUSED = Exception('Cluster Id "320011269" unknown')


class FakeServer:
    """A Matter server's client: refuses the Yeelight clusters unless it
    knows them; records what is sent."""

    def __init__(self, knows_yeelight, nodes=(), version="1.4.0", error=None):
        self.knows_yeelight = knows_yeelight
        self.nodes = list(nodes)
        self.server_info = types.SimpleNamespace(sdk_version=version)
        self.error = error
        self.sent = []

    def get_nodes(self):
        return self.nodes

    async def send_command(self, command, **kwargs):
        self.sent.append((command, kwargs["command_name"], kwargs["payload"]))
        if self.error is not None:
            raise self.error
        if not self.knows_yeelight:
            raise REFUSED
        return {"ok": kwargs["command_name"]}

    async def write_attribute(self, node_id, path, value):
        if not self.knows_yeelight:
            raise REFUSED
        self.sent.append(("write", path, value))
        return [{"Status": 0}]


def link_to(client, node_id=2):
    return types.SimpleNamespace(linked=True, client=client, node_id=node_id, mac=None)


def commands(link=None):
    return COMMANDS.MatterCommands(link)


def run(coroutine):
    return asyncio.run(coroutine)


class MatterCommandsTests(unittest.TestCase):
    def test_a_lamp_paired_again_is_checked_again(self):
        # The old node's check timed out (its pairing was erased); the new
        # node is checked as soon as the link moves to it.
        server = FakeServer(knows_yeelight=True, error=TimeoutError())
        link = link_to(server, node_id=7)
        channel = commands(link)
        self.assertFalse(run(channel.async_available()))
        server.error = None
        link.node_id = 8
        self.assertTrue(run(channel.async_available()))
        self.assertEqual(2, len(server.sent))  # one check per node

    def test_without_matter_nothing_is_available(self):
        channel = commands()
        self.assertFalse(run(channel.async_available()))
        self.assertIsNone(channel.backend)
        with self.assertRaises(COMMANDS.MatterCommandsUnavailable):
            run(channel.async_command(COMMANDS.EFFECTS_CLUSTER, "setRate", {"rate": 20}))
        with self.assertRaises(COMMANDS.MatterCommandsUnavailable):
            run(channel.async_write("2/320011265/319946753", True))

    def test_the_official_server_before_it_knows_the_yeelight_clusters(self):
        official = FakeServer(knows_yeelight=False)
        channel = commands(link_to(official))
        self.assertFalse(run(channel.async_available()))
        # Checked once (getCurrentEffect), not again for every command.
        self.assertFalse(run(channel.async_available()))
        self.assertEqual(1, len(official.sent))
        self.assertEqual("getCurrentEffect", official.sent[0][1])
        # Updated to a version that knows them: checked again, then used.
        official.knows_yeelight = True
        official.server_info.sdk_version = "1.6.0"
        self.assertTrue(run(channel.async_available()))
        self.assertEqual("matter", channel.backend)
        result = run(channel.async_command(COMMANDS.EFFECTS_CLUSTER, "setRate", {"rate": 20}))
        self.assertEqual({"ok": "setRate"}, result)

    def test_a_released_link_no_longer_delivers(self):
        # The node gone from the server (the link released by the minute
        # check): what needs the commands is hidden at once, not only after
        # the next command fails.
        link = link_to(FakeServer(knows_yeelight=True))
        channel = commands(link)
        self.assertTrue(run(channel.async_available()))
        self.assertEqual("matter", channel.backend)
        link.linked = False
        self.assertIsNone(channel.backend)
        link.linked = True
        self.assertEqual("matter", channel.backend)

    def test_why_no_server_delivers(self):
        channel = commands(link_to(FakeServer(knows_yeelight=False)))
        self.assertFalse(run(channel.async_available()))
        self.assertEqual("Home Assistant's Matter server does not know the Yeelight clusters", channel.reason)
        channel = commands()
        self.assertFalse(run(channel.async_available()))
        self.assertEqual("the lamp is not linked to Home Assistant's Matter integration", channel.reason)
        channel = commands(link_to(FakeServer(knows_yeelight=True)))
        self.assertTrue(run(channel.async_available()))
        self.assertIsNone(channel.reason)

    def test_only_home_assistant_s_server_is_used(self):
        # The development server is gone: Home Assistant's own delivers the
        # Yeelight commands (matterjs-server 1.5.4 and later).
        source = Path(COMMANDS.__file__).read_text(encoding="utf-8")
        self.assertNotIn("matter_dev_server", source)
        self.assertNotIn("dev", COMMANDS.MatterCommands.__init__.__code__.co_varnames)

    def test_a_lamp_that_does_not_answer_is_checked_again_later(self):
        official = FakeServer(knows_yeelight=True, error=TimeoutError("no answer"))
        channel = commands(link_to(official))
        self.assertFalse(run(channel.async_available()))
        self.assertIn("could not be checked (no answer)", channel.reason)
        official.error = None
        # Not for every command: after CHECK_RETRY (a minute: usually the
        # lamp rebooting or busy, not the server).
        self.assertFalse(run(channel.async_available()))
        self.assertEqual(1, len(official.sent))
        channel._check_again_at = {key: 0.0 for key in channel._check_again_at}
        self.assertTrue(run(channel.async_available()))

    def test_a_server_that_never_answers_is_given_up_on(self):
        class Silent(FakeServer):
            async def send_command(self, command, **kwargs):
                await asyncio.sleep(3600)

        with patch.object(COMMANDS, "CHECK_TIMEOUT", 0.05):
            channel = commands(link_to(Silent(knows_yeelight=True)))
            self.assertFalse(run(channel.async_available()))
        self.assertIn("could not be checked", channel.reason)

    def test_other_errors_reach_the_caller(self):
        official = FakeServer(knows_yeelight=True)
        channel = commands(link_to(official))
        self.assertTrue(run(channel.async_available()))
        official.error = TimeoutError("no answer")
        with self.assertRaises(TimeoutError):
            run(channel.async_command(COMMANDS.EFFECTS_CLUSTER, "setRate", {"rate": 20}))

    def test_refusals_are_recognised(self):
        self.assertTrue(COMMANDS.refuses_yeelight(REFUSED))
        self.assertTrue(COMMANDS.refuses_yeelight(Exception('Command "setRate" does not exist on cluster')))
        self.assertFalse(COMMANDS.refuses_yeelight(TimeoutError("no answer")))
        self.assertTrue(COMMANDS.refuses_yeelight(
            Exception('Command "getCurrentEffect" does not exist on cluster "yeelightEffects"')
        ))
        self.assertTrue(COMMANDS.refuses_yeelight(Exception("Attribute 319946753 on cluster 320011265 unknown")))
        # Errors that cannot tell: not taken for a server without the clusters.
        self.assertFalse(COMMANDS.refuses_yeelight(Exception("Unknown error")))
        self.assertFalse(COMMANDS.refuses_yeelight(Exception("Node 2 does not exist")))

    def test_an_unclear_error_is_checked_again_not_cached_for_good(self):
        # A node being interviewed again: "does not exist" does not mean the
        # server lacks the Yeelight clusters.
        official = FakeServer(knows_yeelight=True, error=Exception("Node 2 does not exist"))
        channel = commands(link_to(official))
        self.assertFalse(run(channel.async_available()))
        self.assertIn("could not be checked", channel.reason)
        official.error = None
        channel._check_again_at = {key: 0.0 for key in channel._check_again_at}
        self.assertTrue(run(channel.async_available()))

    def test_commands_sent_together_share_one_check(self):
        class Slow(FakeServer):
            async def send_command(self, command, **kwargs):
                if kwargs["command_name"] == "getCurrentEffect":
                    await asyncio.sleep(0.01)
                return await super().send_command(command, **kwargs)

        server = Slow(knows_yeelight=True)
        channel = commands(link_to(server))

        async def together():
            return await asyncio.gather(
                channel.async_command(COMMANDS.EFFECTS_CLUSTER, "setRate", {"rate": 20}),
                channel.async_command(COMMANDS.EFFECTS_CLUSTER, "setRate", {"rate": 30}),
            )

        run(together())
        self.assertEqual(1, sum(1 for _c, name, _p in server.sent if name == "getCurrentEffect"))


if __name__ == "__main__":
    unittest.main()
