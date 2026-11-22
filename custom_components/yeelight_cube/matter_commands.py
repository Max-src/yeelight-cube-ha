"""Yeelight writes and commands to a lamp over Matter (optional).

Home Assistant's Matter server reads the lamp's Yeelight clusters
(matter_link.py); it writes them and sends their commands from
matterjs-server 1.5.4 (matter-js/matterjs-server#1203), and refuses them
before. Whether it delivers them to the lamp is checked with a read-only
command (getCurrentEffect), again after the server changes; when it does
not (an older server, no Matter), MatterCommandsUnavailable is caught to
fall back to LAN or to hide what needs it. Lamps without Matter stay as
they are.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Any

from .matter_link import (
    VENDOR_ENDPOINT,
    MatterLink,
    _vendor,
)

_LOGGER = logging.getLogger(__name__)

CUBE_CONTROL_CLUSTER = _vendor(0xFC02)
EFFECTS_CLUSTER = _vendor(0xFC05)

# Seconds the server check (getCurrentEffect) may take; a check that cannot
# tell (no answer, an unknown error) is tried again after CHECK_RETRY. It is
# usually the lamp, not the server: rebooting after a power cycle (its Matter
# session takes a few minutes to come back), or busy.
CHECK_TIMEOUT = 5.0
CHECK_RETRY = 60.0

# How a server without the Yeelight clusters refuses a command or a write
# (matterjs-server's ControllerCommandHandler): 'Cluster Id "<id>" unknown',
# 'Command "<name>" does not exist on cluster "<name>"', 'Attribute <id> on
# cluster <id> unknown'. Other errors ("Unknown error", a node that does not
# exist while it is interviewed again) cannot tell: checked again later.
_UNKNOWN_CLUSTER_PATTERNS = (
    re.compile(r'cluster id "?[^"\s]+"? unknown'),
    re.compile(r'command "?[^"\s]+"? does not exist on cluster'),
    re.compile(r'attribute \S+ on cluster \S+ unknown'),
)


class MatterCommandsUnavailable(Exception):
    """No Matter server can deliver Yeelight commands to the lamp."""


def refuses_yeelight(error: Exception) -> bool:
    """Whether a server's error means it does not know the Yeelight clusters."""
    text = str(error).lower()
    return any(pattern.search(text) for pattern in _UNKNOWN_CLUSTER_PATTERNS)


def _server_key(client) -> tuple[int, Any]:
    """A server as reached through a client: the client, and the server's
    version (a server update is checked again)."""
    info = getattr(client, "server_info", None)
    return id(client), getattr(info, "sdk_version", None)


class MatterCommands:
    """Yeelight writes and commands to one lamp, through Home Assistant's
    Matter server when it delivers them (see the module docstring).

    ``backend``: "matter" (Home Assistant's server) or None (it does not
    deliver them yet, or the link was released since); ``reason``: why not,
    None when it does.
    """

    def __init__(self, link: MatterLink | None) -> None:
        self._link = link
        # Servers checked: their key (_server_key) -> whether they deliver.
        self._checked: dict[tuple[int, Any], bool] = {}
        # Servers whose check could not tell: when to check them again.
        self._check_again_at: dict[tuple[int, Any], float] = {}
        self._backend: str | None = None
        self.reason: str | None = None
        self._check_error: str | None = None
        # One check at a time: commands sent together wait for the first's.
        self._check_lock = asyncio.Lock()

    @property
    def backend(self) -> str | None:
        # The link released (the node gone from the server): no longer
        # delivered, though no command has been tried since.
        link = self._link
        if link is None or not link.linked:
            return None
        return self._backend

    @backend.setter
    def backend(self, value: str | None) -> None:
        self._backend = value

    async def _route(self) -> tuple[str, Any, int]:
        """(backend, client, node id) of the server that delivers."""
        reasons: list[str] = []
        link = self._link
        if link is not None and link.linked and link.client is not None:
            # Per node too: a lamp paired again is a new node to check.
            client, node_id = link.client, link.node_id
            key = (*_server_key(client), node_id)
            if self._needs_check(key):
                async with self._check_lock:
                    if self._needs_check(key):  # not checked meanwhile
                        delivers = await self._delivers(client, node_id)
                        if delivers is None:  # could not tell: checked again later
                            self._check_again_at[key] = time.monotonic() + CHECK_RETRY
                        else:
                            self._checked[key] = delivers
            if self._checked.get(key):
                self.reason = None
                return "matter", link.client, link.node_id
            reasons.append(
                "Home Assistant's Matter server does not know the Yeelight clusters"
                if key in self._checked
                else f"Home Assistant's Matter server could not be checked ({self._check_error})"
            )
        else:
            reasons.append("the lamp is not linked to Home Assistant's Matter integration")
        self.backend = None
        self.reason = "; ".join(reasons)
        raise MatterCommandsUnavailable(
            f"No Matter server can send Yeelight commands to this lamp: {self.reason}"
        )

    def _needs_check(self, key: tuple[int, Any, int]) -> bool:
        return key not in self._checked and time.monotonic() >= self._check_again_at.get(key, 0.0)

    async def _delivers(self, client, node_id: int) -> bool | None:
        """Whether a server knows the Yeelight clusters (a read-only
        command); None when it could not tell (the lamp did not answer)."""
        try:
            await asyncio.wait_for(
                self._send(client, node_id, EFFECTS_CLUSTER, "getCurrentEffect", {}),
                CHECK_TIMEOUT,
            )
        except Exception as err:  # noqa: BLE001 -- refused, no answer, timeout
            if refuses_yeelight(err):
                return False
            _LOGGER.debug("Yeelight Matter check failed: %s", err)
            self._check_error = str(err) or type(err).__name__
            return None
        return True

    @staticmethod
    async def _send(client, node_id: int, cluster_id: int, name: str, payload: dict,
                    endpoint_id: int = VENDOR_ENDPOINT):
        return await client.send_command(
            "device_command",
            node_id=node_id,
            endpoint_id=endpoint_id,
            cluster_id=cluster_id,
            command_name=name,
            payload=payload,
        )

    async def async_available(self) -> bool:
        """Whether some server delivers Yeelight commands to the lamp now."""
        try:
            self.backend = (await self._route())[0]
        except MatterCommandsUnavailable:
            return False
        return True

    async def async_command(self, cluster_id: int, name: str, payload: dict | None = None,
                            endpoint_id: int = VENDOR_ENDPOINT):
        """Send a Yeelight command (field names as in the cluster definition;
        a standard cluster's on its own endpoint); returns its response, if
        any. MatterCommandsUnavailable: no server."""
        backend, client, node_id = await self._route()
        self.backend = backend
        return await self._send(client, node_id, cluster_id, name, payload or {}, endpoint_id)

    async def async_write(self, path: str, value) -> Any:
        """Write a Yeelight attribute ("endpoint/cluster/attribute", as
        matter_link's paths). MatterCommandsUnavailable: no server."""
        backend, client, node_id = await self._route()
        self.backend = backend
        return await client.write_attribute(node_id, path, value)
