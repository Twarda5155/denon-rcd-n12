"""Command-layer tests. Runs with the receiver powered off."""

from __future__ import annotations

import unittest

from fakes import FakeHeosTransport, FakeTelnetTransport

from denon_rcd_n12 import client as client_module
from denon_rcd_n12.client import (
    FAVORITES_SID,
    PLAY_STATES,
    SELECTABLE_SOURCES,
    SOURCE_NET,
    SOURCE_SERVER,
    SOURCES,
    VOLUME_MAX,
    VOLUME_MIN,
    VOLUME_STEP_MAX,
    VOLUME_STEP_MIN,
    DenonClient,
)
from denon_rcd_n12.transport import DeviceError, _parse_flat_yaml, heos_message


def build(
    power: str = "on",
    volume: int = 20,
    mute: bool = False,
    heartbeat: bool = False,
    fail: bool = False,
    source: str = "SICD",
    now_playing_sid: int | None = 1024,
    play_state: str = "play",
) -> tuple[DenonClient, FakeTelnetTransport, FakeHeosTransport]:
    """Assemble a client over fresh fakes.

    Args:
        power: Initial power state of the fake AVR endpoint.
        volume: HEOS level the fake reports.
        mute: Mute state the fake reports.
        heartbeat: Interleave a stale ``PW`` frame into AVR replies.
        fail: Make both transports unreachable.
        source: Initial ``SI`` token of the fake AVR endpoint.
        now_playing_sid: HEOS source id the fake reports as playing, which
            selects the recorded metadata payload.
        play_state: Transport state the fake reports.

    Returns:
        The client and both fakes, so tests can assert on recorded commands.
    """
    telnet = FakeTelnetTransport(
        power=power, heartbeat=heartbeat, fail=fail, source=source
    )
    heos = FakeHeosTransport(
        volume=volume,
        mute=mute,
        fail=fail,
        now_playing_sid=now_playing_sid,
        play_state=play_state,
    )
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

    def test_set_volume_writes_then_reads_back(self) -> None:
        client, _, heos = build(volume=20)
        self.assertEqual(client.set_volume(55), {"volume": 55, "mute": False})
        self.assertEqual(heos.volume, 55)

    def test_set_volume_sends_the_level_to_the_configured_player(self) -> None:
        client, _, heos = build()
        client.set_volume(7)
        self.assertEqual(
            heos.commands[0], f"heos://player/set_volume?pid={heos.pid}&level=7"
        )

    def test_set_volume_reports_mute_alongside_the_new_level(self) -> None:
        # The reply carries the whole volume state, so a muted unit stays
        # visibly muted after a level change rather than silently dropping it.
        client, _, _ = build(mute=True)
        self.assertEqual(client.set_volume(30), {"volume": 30, "mute": True})

    def test_set_volume_accepts_the_scale_bounds(self) -> None:
        for level in (VOLUME_MIN, VOLUME_MAX):
            with self.subTest(level=level):
                client, _, _ = build()
                self.assertEqual(client.set_volume(level)["volume"], level)

    def test_set_volume_rejects_out_of_range_levels(self) -> None:
        for level in (-1, 101):
            with self.subTest(level=level):
                client, _, heos = build()
                with self.assertRaises(ValueError):
                    client.set_volume(level)
                self.assertEqual(heos.commands, [])

    def test_set_volume_rejects_non_integer_levels(self) -> None:
        client, _, heos = build()
        with self.assertRaises(ValueError):
            client.set_volume("40")  # type: ignore[arg-type]
        self.assertEqual(heos.commands, [])

    def test_set_volume_never_touches_the_telnet_transport(self) -> None:
        client, telnet, _ = build()
        client.set_volume(12)
        self.assertEqual(telnet.commands, [])

    def test_set_volume_on_unreachable_device_raises(self) -> None:
        client, _, _ = build(fail=True)
        with self.assertRaises(DeviceError):
            client.set_volume(30)


class VolumeStepTests(unittest.TestCase):
    """Relative volume changes over HEOS."""

    def test_step_up_and_down(self) -> None:
        client, _, heos = build(volume=20)
        self.assertEqual(client.step_volume("up")["volume"], 21)
        self.assertEqual(client.step_volume("down")["volume"], 20)
        self.assertEqual(heos.volume, 20)

    def test_step_size_is_sent(self) -> None:
        client, _, heos = build(volume=20)
        self.assertEqual(client.step_volume("up", 10)["volume"], 30)
        self.assertIn(
            f"heos://player/volume_up?pid={heos.pid}&step=10", heos.commands
        )

    def test_step_accepts_the_bounds(self) -> None:
        for step in (VOLUME_STEP_MIN, VOLUME_STEP_MAX):
            with self.subTest(step=step):
                client, _, _ = build(volume=50)
                client.step_volume("up", step)

    def test_step_rejects_sizes_outside_the_range(self) -> None:
        for step in (0, VOLUME_STEP_MAX + 1, -1):
            with self.subTest(step=step):
                client, _, heos = build()
                with self.assertRaises(ValueError):
                    client.step_volume("up", step)
                self.assertEqual(heos.commands, [])

    def test_step_rejects_an_unknown_direction(self) -> None:
        client, _, heos = build()
        with self.assertRaises(ValueError):
            client.step_volume("sideways")
        self.assertEqual(heos.commands, [])

    def test_step_reports_mute_alongside_the_new_level(self) -> None:
        client, _, _ = build(volume=20, mute=True)
        self.assertEqual(client.step_volume("up"), {"volume": 21, "mute": True})

    def test_step_never_touches_the_telnet_transport(self) -> None:
        client, telnet, _ = build()
        client.step_volume("up")
        self.assertEqual(telnet.commands, [])

    def test_step_on_unreachable_device_raises(self) -> None:
        client, _, _ = build(fail=True)
        with self.assertRaises(DeviceError):
            client.step_volume("up")


class MuteTests(unittest.TestCase):
    """Mute as a write, measured on the device 2026-09-08."""

    def test_set_mute_on_and_off(self) -> None:
        client, _, heos = build(mute=False)
        self.assertEqual(client.set_mute(True)["mute"], True)
        self.assertEqual(heos.mute, True)
        self.assertEqual(client.set_mute(False)["mute"], False)
        self.assertEqual(heos.mute, False)

    def test_set_mute_addresses_the_configured_player(self) -> None:
        client, _, heos = build(mute=False)
        client.set_mute(True)
        self.assertIn(
            f"heos://player/set_mute?pid={heos.pid}&state=on", heos.commands
        )

    def test_set_mute_reports_the_level_alongside(self) -> None:
        client, _, _ = build(volume=42, mute=False)
        self.assertEqual(client.set_mute(True), {"volume": 42, "mute": True})

    def test_toggle_mute_flips_either_way(self) -> None:
        client, _, _ = build(mute=False)
        self.assertEqual(client.toggle_mute()["mute"], True)
        client, _, _ = build(mute=True)
        self.assertEqual(client.toggle_mute()["mute"], False)

    def test_mute_never_touches_the_telnet_transport(self) -> None:
        client, telnet, _ = build()
        client.toggle_mute()
        self.assertEqual(telnet.commands, [])

    def test_mute_on_unreachable_device_raises(self) -> None:
        client, _, _ = build(fail=True)
        with self.assertRaises(DeviceError):
            client.toggle_mute()


class SourceTests(unittest.TestCase):
    """Input selection over the AVR protocol, disambiguated through HEOS."""

    def setUp(self) -> None:
        """Collapse the post-write settle delay so the suite stays fast."""
        original = client_module.SOURCE_SETTLE_S
        client_module.SOURCE_SETTLE_S = 0.0
        self.addCleanup(setattr, client_module, "SOURCE_SETTLE_S", original)

    def test_get_source_maps_every_measured_token(self) -> None:
        for name, token in SOURCES.items():
            with self.subTest(name=name):
                # SINET is the one token that also needs HEOS; a streaming sid
                # keeps this case on the plain 'net' answer.
                client, telnet, _ = build(source=token, now_playing_sid=3)
                self.assertEqual(client.get_source(), name)
                self.assertEqual(telnet.commands, ["SI?"])

    def test_get_source_ignores_stale_heartbeat_frame(self) -> None:
        client, _, _ = build(source="SIANALOG1", heartbeat=True)
        self.assertEqual(client.get_source(), "aux")

    def test_get_source_without_si_frame_raises(self) -> None:
        client, telnet, _ = build()
        telnet.send = lambda *a, **k: ["PWON"]  # type: ignore[method-assign]
        with self.assertRaises(DeviceError):
            client.get_source()

    def test_get_source_rejects_unmeasured_token(self) -> None:
        # Token sets differ by model; a token this unit was never seen
        # returning is reported rather than guessed at.
        client, telnet, _ = build()
        telnet.send = lambda *a, **k: ["SIBT"]  # type: ignore[method-assign]
        with self.assertRaises(DeviceError):
            client.get_source()

    def test_get_source_reports_server_for_local_media(self) -> None:
        # SINET covers both a streaming service and a DLNA server; only the
        # HEOS source id tells them apart.
        client, _, _ = build(source="SINET", now_playing_sid=1024)
        self.assertEqual(client.get_source(), SOURCE_SERVER)

    def test_get_source_reports_net_for_a_streaming_service(self) -> None:
        client, _, _ = build(source="SINET", now_playing_sid=3)
        self.assertEqual(client.get_source(), "net")

    def test_get_source_reports_net_when_nothing_is_playing(self) -> None:
        client, _, _ = build(source="SINET", now_playing_sid=None)
        self.assertEqual(client.get_source(), "net")

    def test_get_source_asks_heos_only_for_the_network_input(self) -> None:
        client, _, heos = build(source="SICD")
        client.get_source()
        self.assertEqual(heos.commands, [])

    def test_get_source_asks_heos_for_the_network_input(self) -> None:
        client, _, heos = build(source="SINET")
        client.get_source()
        self.assertEqual(
            heos.commands,
            [f"heos://player/get_now_playing_media?pid={heos.pid}"],
        )

    def test_set_source_writes_then_reads_back(self) -> None:
        client, telnet, _ = build(source="SICD")
        self.assertEqual(client.set_source("phono"), "phono")
        self.assertEqual(telnet.commands, ["SI?", "SIANALOGPHONO", "SI?"])
        self.assertEqual(telnet.source, "SIANALOGPHONO")

    def test_set_source_skips_write_when_already_on_the_input(self) -> None:
        client, telnet, _ = build(source="SICD")
        self.assertEqual(client.set_source("cd"), "cd")
        self.assertEqual(telnet.commands, ["SI?"])

    def test_set_source_rejects_both_network_names(self) -> None:
        # Measured 2026-09-08: the unit ignores SINET as a write. Reporting the
        # input it failed to leave would read as a broken control, so neither
        # name is accepted and the caller is told why.
        for name in (SOURCE_NET, SOURCE_SERVER):
            with self.subTest(name=name):
                client, telnet, _ = build(source="SICD")
                with self.assertRaises(ValueError):
                    client.set_source(name)
                self.assertEqual(telnet.commands, [])

    def test_set_source_rejects_net_even_while_the_unit_is_on_it(self) -> None:
        # No "already there, nothing to do" shortcut: the name is unwritable,
        # and answering as though it had worked would teach a caller otherwise.
        client, telnet, _ = build(source="SINET", now_playing_sid=1024)
        with self.assertRaises(ValueError):
            client.set_source(SOURCE_NET)
        self.assertEqual(telnet.commands, [])

    def test_selectable_sources_are_the_inputs_minus_the_network(self) -> None:
        self.assertNotIn(SOURCE_NET, SELECTABLE_SOURCES)
        self.assertEqual(
            set(SELECTABLE_SOURCES), set(SOURCES) - {SOURCE_NET}
        )

    def test_get_source_still_reports_the_network_names(self) -> None:
        # Unwritable is not unreadable: both network states remain things the
        # unit can be found in.
        client, _, _ = build(source="SINET", now_playing_sid=3)
        self.assertEqual(client.get_source(), SOURCE_NET)
        client, _, _ = build(source="SINET", now_playing_sid=1024)
        self.assertEqual(client.get_source(), SOURCE_SERVER)

    def test_set_source_rejects_unknown_name(self) -> None:
        client, telnet, _ = build()
        with self.assertRaises(ValueError):
            client.set_source("bluetooth")
        self.assertEqual(telnet.commands, [])

    def test_set_source_rejects_a_raw_token(self) -> None:
        client, telnet, _ = build()
        with self.assertRaises(ValueError):
            client.set_source("SICD")
        self.assertEqual(telnet.commands, [])

    def test_source_on_unreachable_device_raises(self) -> None:
        client, _, _ = build(fail=True)
        with self.assertRaises(DeviceError):
            client.get_source()

    def test_every_source_name_maps_to_one_token(self) -> None:
        # SINET is deliberately shared with the server sense of the input, but
        # no other token may be; the reverse map depends on it.
        tokens = [t for name, t in SOURCES.items()]
        self.assertEqual(len(tokens), len(set(tokens)))


class PlaybackTests(unittest.TestCase):
    """Transport state and now-playing metadata over HEOS."""

    def test_reports_the_transport_state(self) -> None:
        for state in PLAY_STATES:
            with self.subTest(state=state):
                client, _, _ = build(play_state=state)
                self.assertEqual(client.get_playback()["state"], state)

    def test_title_comes_from_song_for_a_track(self) -> None:
        client, _, _ = build(now_playing_sid=1024)
        playing = client.get_playback()
        self.assertEqual(playing["title"], "W oczekiwaniu wiosny")
        self.assertEqual(playing["artist"], "Leszek Dlugosz")
        self.assertEqual(playing["album"], "Dlugosz")
        self.assertEqual(playing["media_type"], "song")

    def test_a_track_carries_no_station(self) -> None:
        client, _, _ = build(now_playing_sid=1024)
        self.assertIsNone(client.get_playback()["station"])

    def test_a_stream_reports_track_and_station_separately(self) -> None:
        # The recorded TuneIn payload fills in both: 'song' is what is on air,
        # 'station' is the station carrying it. Folding one into the other
        # would lose whichever the page then wanted to show.
        client, _, _ = build(now_playing_sid=3)
        playing = client.get_playback()
        self.assertEqual(playing["title"], "Deutschland national")
        self.assertEqual(playing["station"], "Klassik Radio")
        self.assertEqual(playing["media_type"], "station")

    def test_empty_album_is_reported_as_absent(self) -> None:
        # The stream recording carries album as an empty string, which is not
        # a value worth putting on the page.
        client, _, _ = build(now_playing_sid=3)
        self.assertIsNone(client.get_playback()["album"])

    def test_player_with_no_media_reports_state_only(self) -> None:
        client, _, _ = build(now_playing_sid=None, play_state="stop")
        self.assertEqual(
            client.get_playback(),
            {
                "state": "stop",
                "title": None,
                "artist": None,
                "album": None,
                "station": None,
                "media_type": None,
            },
        )

    def test_unknown_is_a_state_this_unit_reports(self) -> None:
        # Undocumented in the HEOS reference, but measured at every transition
        # on this unit: a caller that treats it as an error would flag a normal
        # input change as a failure.
        self.assertIn("unknown", PLAY_STATES)
        client, _, _ = build(play_state="unknown")
        self.assertEqual(client.get_playback()["state"], "unknown")

    def test_metadata_survives_a_stopped_transport(self) -> None:
        # Measured on the device 2026-09-07: a sleeping unit still reports the
        # last track it played, at state 'stop'. The client must not scrub the
        # metadata on the strength of the state -- reporting both is what lets
        # the page say 'stopped' next to a title rather than pretend it plays.
        client, _, _ = build(now_playing_sid=1024, play_state="stop")
        playing = client.get_playback()
        self.assertEqual(playing["state"], "stop")
        self.assertEqual(playing["title"], "W oczekiwaniu wiosny")

    def test_addresses_the_configured_player(self) -> None:
        client, _, heos = build()
        client.get_playback()
        self.assertEqual(
            heos.commands,
            [
                f"heos://player/get_play_state?pid={heos.pid}",
                f"heos://player/get_now_playing_media?pid={heos.pid}",
            ],
        )

    def test_never_touches_the_telnet_transport(self) -> None:
        client, telnet, _ = build()
        client.get_playback()
        self.assertEqual(telnet.commands, [])

    def test_on_unreachable_device_raises(self) -> None:
        client, _, _ = build(fail=True)
        with self.assertRaises(DeviceError):
            client.get_playback()


class FavoritesTests(unittest.TestCase):
    """Listing the favourites the receiver holds, and starting one."""

    def setUp(self) -> None:
        """Collapse the post-start settle delay so the suite stays fast."""
        original = client_module.FAVORITE_SETTLE_S
        client_module.FAVORITE_SETTLE_S = 0.0
        self.addCleanup(setattr, client_module, "FAVORITE_SETTLE_S", original)

    def test_lists_the_recorded_favorites(self) -> None:
        client, _, _ = build()
        self.assertEqual(
            client.list_favorites(),
            [
                {
                    "name": "1.FM Gaia",
                    "mid": "s214674",
                    "media_type": "station",
                    "playable": True,
                },
                {
                    "name": "Klassik Radio",
                    "mid": "s25028",
                    "media_type": "station",
                    "playable": True,
                },
            ],
        )

    def test_browses_the_favorites_source(self) -> None:
        client, _, heos = build()
        client.list_favorites()
        self.assertEqual(
            heos.commands, [f"heos://browse/browse?sid={FAVORITES_SID}"]
        )

    def test_a_receiver_with_no_favorites_lists_nothing(self) -> None:
        telnet = FakeTelnetTransport()
        heos = FakeHeosTransport(favorites=[])
        self.assertEqual(DenonClient(telnet, heos).list_favorites(), [])

    def test_never_touches_the_telnet_transport(self) -> None:
        client, telnet, _ = build()
        client.list_favorites()
        self.assertEqual(telnet.commands, [])

    def test_on_unreachable_device_raises(self) -> None:
        client, _, _ = build(fail=True)
        with self.assertRaises(DeviceError):
            client.list_favorites()

    def test_play_favorite_sends_the_position_as_a_preset(self) -> None:
        client, _, heos = build()
        client.play_favorite(2)
        self.assertEqual(
            heos.commands[0],
            f"heos://browse/play_preset?pid={heos.pid}&preset=2",
        )

    def test_play_favorite_reports_what_is_playing_afterwards(self) -> None:
        client, _, _ = build(play_state="play")
        self.assertEqual(client.play_favorite(1)["state"], "play")

    def test_play_favorite_rejects_positions_below_one(self) -> None:
        # HEOS numbers favourites from one, so zero and negatives are caller
        # bugs worth naming here rather than round trips for the device to
        # refuse.
        for position in (0, -1):
            with self.subTest(position=position):
                client, _, heos = build()
                with self.assertRaises(ValueError):
                    client.play_favorite(position)
                self.assertEqual(heos.commands, [])

    def test_play_favorite_rejects_a_non_integer_position(self) -> None:
        client, _, heos = build()
        with self.assertRaises(ValueError):
            client.play_favorite("1")  # type: ignore[arg-type]
        self.assertEqual(heos.commands, [])

    def test_play_favorite_never_touches_the_telnet_transport(self) -> None:
        client, telnet, _ = build()
        client.play_favorite(1)
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
