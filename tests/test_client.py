"""Command-layer tests. Runs with the receiver powered off."""

from __future__ import annotations

import unittest

from fakes import FakeHeosTransport, FakeTelnetTransport

from denon_rcd_n12 import client as client_module
from denon_rcd_n12.client import DenonClient
from denon_rcd_n12.transport import DeviceError, _parse_flat_yaml, heos_message


def build(
    power: str = "on",
    volume: int = 20,
    mute: bool = False,
    heartbeat: bool = False,
    fail: bool = False,
) -> tuple[DenonClient, FakeTelnetTransport, FakeHeosTransport]:
    """Assemble a client over fresh fakes.

    Args:
        power: Initial power state of the fake AVR endpoint.
        volume: HEOS level the fake reports.
        mute: Mute state the fake reports.
        heartbeat: Interleave a stale ``PW`` frame into AVR replies.
        fail: Make both transports unreachable.

    Returns:
        The client and both fakes, so tests can assert on recorded commands.
    """
    telnet = FakeTelnetTransport(power=power, heartbeat=heartbeat, fail=fail)
    heos = FakeHeosTransport(volume=volume, mute=mute, fail=fail)
    return DenonClient(telnet, heos), telnet, heos


class PowerTests(unittest.TestCase):
    """Power query, write and toggle."""

    def setUp(self) -> None:
        """Collapse the post-command settle delays so the suite stays fast."""
        for name in ("WAKE_SETTLE_S", "SLEEP_SETTLE_S"):
            original = getattr(client_module, name)
            setattr(client_module, name, 0.0)
            self.addCleanup(setattr, client_module, name, original)

    def test_get_power_reads_on(self) -> None:
        client, telnet, _ = build(power="on")
        self.assertEqual(client.get_power(), "on")
        self.assertEqual(telnet.commands, ["PW?"])

    def test_get_power_reads_standby(self) -> None:
        client, _, _ = build(power="standby")
        self.assertEqual(client.get_power(), "standby")

    def test_get_power_ignores_stale_heartbeat_frame(self) -> None:
        # The reply and the ~10 s PW heartbeat share a format and interleave;
        # the most recent frame is the authoritative one.
        client, _, _ = build(power="on", heartbeat=True)
        self.assertEqual(client.get_power(), "on")

    def test_get_power_without_pw_frame_raises(self) -> None:
        client, telnet, _ = build()
        telnet.send = lambda *a, **k: ["MV20"]  # type: ignore[method-assign]
        with self.assertRaises(DeviceError):
            client.get_power()

    def test_set_power_on_from_standby_writes(self) -> None:
        client, telnet, _ = build(power="standby")
        self.assertEqual(client.set_power("on"), "on")
        self.assertEqual(telnet.commands, ["PW?", "PWON", "PW?"])

    def test_set_power_skips_write_when_already_in_state(self) -> None:
        client, telnet, _ = build(power="on")
        self.assertEqual(client.set_power("on"), "on")
        self.assertEqual(telnet.commands, ["PW?"])

    def test_set_power_rejects_unknown_state(self) -> None:
        client, _, _ = build()
        with self.assertRaises(ValueError):
            client.set_power("off")

    def test_toggle_from_on_goes_to_standby(self) -> None:
        client, telnet, _ = build(power="on")
        self.assertEqual(client.toggle_power(), "standby")
        self.assertIn("PWSTANDBY", telnet.commands)

    def test_toggle_from_standby_goes_to_on(self) -> None:
        client, telnet, _ = build(power="standby")
        self.assertEqual(client.toggle_power(), "on")
        self.assertIn("PWON", telnet.commands)

    def test_unreachable_device_raises(self) -> None:
        client, _, _ = build(fail=True)
        with self.assertRaises(DeviceError):
            client.get_power()

    def test_power_never_touches_the_heos_transport(self) -> None:
        # Power lives on the AVR protocol only; HEOS has no such command.
        client, _, heos = build(power="on")
        client.get_power()
        self.assertEqual(heos.commands, [])


class VolumeTests(unittest.TestCase):
    """Volume and mute over HEOS."""

    def test_get_volume(self) -> None:
        client, _, _ = build(volume=37, mute=False)
        self.assertEqual(client.get_volume(), {"volume": 37, "mute": False})

    def test_get_volume_reports_mute(self) -> None:
        client, _, _ = build(mute=True)
        self.assertTrue(client.get_volume()["mute"])

    def test_get_volume_addresses_the_configured_player(self) -> None:
        client, _, heos = build()
        client.get_volume()
        self.assertTrue(all(f"pid={heos.pid}" in c for c in heos.commands))

    def test_get_volume_on_unreachable_device_raises(self) -> None:
        client, _, _ = build(fail=True)
        with self.assertRaises(DeviceError):
            client.get_volume()

    def test_volume_never_touches_the_telnet_transport(self) -> None:
        # Volume lives on HEOS; the AVR MV scale is a different scale entirely.
        client, telnet, _ = build()
        client.get_volume()
        self.assertEqual(telnet.commands, [])


class ParsingTests(unittest.TestCase):
    """Helpers in the transport module that touch no socket."""

    def test_heos_message_splits_parameters(self) -> None:
        obj = {"heos": {"message": "pid=1&level=42"}}
        self.assertEqual(heos_message(obj), {"pid": "1", "level": "42"})

    def test_flat_yaml_parses_device_config_shape(self) -> None:
        cfg = _parse_flat_yaml(
            "device:\n"
            "  host: 192.0.2.10\n"
            "  heos_pid: 1234567890\n"
            "ports:\n"
            "  heos: 1255\n"
            "  avr: 23\n"
        )
        self.assertEqual(cfg["device"]["host"], "192.0.2.10")
        self.assertEqual(cfg["ports"]["avr"], 23)


if __name__ == "__main__":
    unittest.main()
