from __future__ import absolute_import, print_function, unicode_literals

from ableton.v2.control_surface import ControlSurface
from ableton.v2.control_surface.elements import ButtonElement

MIDI_NOTE_TYPE = 0  # NOTE messages

# -------------------------
# CLIP GRID (your requirement)
# -------------------------
GRID_TRACKS = 8
GRID_SCENES = 4  # limited to 8x4 (top 4 rows)

# -------------------------
# PERFORMANCE MODE NOTES (your confirmed values)
# -------------------------
TRACK_STOP_NOTES = [48, 49, 50, 51, 80, 81, 82, 83]
TRACK_MUTE_NOTES = [44, 45, 46, 47, 76, 77, 78, 79]

NAV_NOTES = {"up": 74, "down": 70, "left": 69, "right": 71}

TRANSPORT_NOTES = {"play": 36, "stop": 37}

SCENE_NOTES = {"left": 38, "play": 39, "right": 68}

TRACK_SELECT_NOTES = {"left": 73, "right": 75}

# -------------------------
# FIXED LED COLORS (0..127) - tweak later if you want
# -------------------------
LED_WHITE = 3
LED_YELLOW = 84
LED_PURPLE = 90
LED_GREEN = 76
LED_BLUE = 65
LED_PINK = 94
LED_RED = 5

MOMENTARY_FLASH_TICKS = 2  # short flash then restore


def note_for_position(row_top_to_bottom, col_left_to_right):
    # Confirmed Mystrix layout:
    # Top row: 64,65,66,67,96,97,98,99
    # Left col: 64,60,56,52,48,44,40,36
    base_top_left = 64
    row_offset = row_top_to_bottom * 4  # -4 each row down
    if col_left_to_right < 4:
        return base_top_left + col_left_to_right - row_offset
    return (base_top_left + 32) + (col_left_to_right - 4) - row_offset


def _safe_get(obj, name, default=None):
    v = getattr(obj, name, default)
    try:
        if callable(v):
            return v()
    except Exception:
        return default
    return v


def _rgb_from_int(rgb_int):
    # Live uses 24-bit RGB ints (0xRRGGBB)
    r = (rgb_int >> 16) & 0xFF
    g = (rgb_int >> 8) & 0xFF
    b = (rgb_int >> 0) & 0xFF
    return r, g, b


# --- Copied from Ableton v3 control_surface/colors.py (your paste) ---
STANDARD_COLOR_PALETTE = {
    10927616: 74,
    16149507: 84,
    4047616: 76,
    6441901: 69,
    14402304: 99,
    8754719: 19,
    16725558: 5,
    3947580: 71,
    10056267: 15,
    8237133: 18,
    12026454: 11,
    12565097: 73,
    13381230: 58,
    12243060: 111,
    16249980: 13,
    13013643: 4,
    10208397: 88,
    695438: 65,
    13821080: 110,
    3101346: 46,
    16749734: 107,
    8962746: 102,
    5538020: 79,
    13684944: 117,
    15064289: 119,
    14183652: 94,
    11442405: 44,
    13408551: 100,
    1090798: 78,
    11096369: 127,
    16753961: 96,
    1769263: 87,
    5480241: 64,
    1698303: 90,
    16773172: 97,
    7491393: 126,
    8940772: 80,
    14837594: 10,
    8912743: 16,
    10060650: 105,
    13872497: 14,
    16753524: 108,
    8092539: 70,
    2319236: 39,
    1716118: 47,
    12349846: 59,
    11481907: 121,
    15029152: 57,
    2490280: 25,
    11119017: 112,
    10701741: 81,
    15597486: 8,
    49071: 77,
    10851765: 93,
    12558270: 48,
    32192: 43,
    8758722: 103,
    10204100: 104,
    11958214: 55,
    8623052: 66,
    16726484: 95,
    12581632: 86,
    13958625: 28,
    12173795: 115,
    13482980: 116,
    16777215: 3,
    6094824: 33,
    13496824: 114,
    9611263: 92,
    9160191: 36,
}

# Precompute list for nearest-color lookup
_PALETTE_ITEMS = list(STANDARD_COLOR_PALETTE.items())  # [(rgb_int, color_id), ...]


def palette_color_id_from_live_rgb(rgb_int):
    """
    Returns a 0..127 'color id' close to Ableton's standard palette.
    If exact match exists, use it; else choose nearest palette entry by RGB distance.
    """
    if rgb_int is None:
        return 0

    try:
        rgb_int = int(rgb_int)
    except Exception:
        return 0

    exact = STANDARD_COLOR_PALETTE.get(rgb_int)
    if exact is not None:
        return exact

    # nearest by squared Euclidean distance in RGB
    r0, g0, b0 = _rgb_from_int(rgb_int)
    best_id = 0
    best_d = None

    for rgb_key, color_id in _PALETTE_ITEMS:
        r1, g1, b1 = _rgb_from_int(rgb_key)
        d = (r0 - r1) * (r0 - r1) + (g0 - g1) * (g0 - g1) + (b0 - b1) * (b0 - b1)
        if best_d is None or d < best_d:
            best_d = d
            best_id = color_id

    return best_id


class Mystrix_Pro(ControlSurface):
    def __init__(self, c_instance):
        super(Mystrix_Pro, self).__init__(c_instance)
        self.show_message("Mystrix_Pro loaded (clips + nav/stop/mute/transport/scene/track)")

        with self.component_guard():
            self._channel = 0  # MIDI ch 1 (0-based)

            # Clip pad buttons
            self._pad_buttons = []

            # Control buttons (stop/mute/nav/transport/scene/track)
            self._control_buttons = []

            # LED cache
            self._led_state = {}   # note -> last velocity sent

            # Notes that must stay always lit (non-clip pads)
            self._fixed_leds = {}  # note -> fixed velocity

            # Nav offsets for the 8x4 window
            self._track_offset = 0
            self._scene_offset = 0
            self._update_red_box()


            # Build listeners
            self._make_pad_listeners()       # clip launch (8x4)
            self._make_control_listeners()   # all fixed pads
            self._apply_fixed_leds()         # force fixed pads on

            # Start LED polling
            self._schedule_led_refresh()

    def _update_red_box(self):
        # Live API: (track_offset, scene_offset, width, height, include_returns)
        try:
            self._c_instance.set_session_highlight(
                int(self._track_offset),
                int(self._scene_offset),
                int(GRID_TRACKS),
                int(GRID_SCENES),
                True
            )
        except Exception:
            # Some builds use a different signature; fail silently
            pass

    # -------------------------
    # Clip pads + launching (UNCHANGED logic, just 8x4 window + offsets in _get_slot)
    # -------------------------
    def _make_pad_listeners(self):
        for scene_index in range(GRID_SCENES):
            for track_index in range(GRID_TRACKS):
                note = note_for_position(scene_index, track_index)

                btn = ButtonElement(
                    True,
                    MIDI_NOTE_TYPE,
                    self._channel,
                    note,
                    name="Pad_T%d_S%d_N%d" % (track_index, scene_index, note),
                )

                btn.add_value_listener(
                    self._make_fire_handler(track_index, scene_index),
                    identify_sender=False,
                )

                self._pad_buttons.append(btn)

    def _make_fire_handler(self, track_index, scene_index):
        def _handler(value):
            if value == 0:
                return
            slot = self._get_slot(track_index, scene_index)
            if slot is None:
                return
            try:
                slot.fire()
            except Exception:
                pass
        return _handler

    # -------------------------
    # Fixed pads: always lit + flash white on press
    # -------------------------
    def _apply_fixed_leds(self):
        for note, vel in self._fixed_leds.items():
            self._send_note(note, vel)
            self._led_state[int(note)] = int(vel)

    def _restore_fixed_led(self, note):
        note = int(note)
        vel = int(self._fixed_leds.get(note, 0)) & 0x7F
        self._send_note(note, vel)
        self._led_state[note] = vel

    def _register_momentary_action(self, note, fixed_vel, action, name):
        note = int(note)

        btn = ButtonElement(True, MIDI_NOTE_TYPE, self._channel, note, name=name)

        # remember fixed color
        self._fixed_leds[note] = int(fixed_vel) & 0x7F

        def _handler(value):
            if value == 0:
                return

            # flash white
            self._send_note(note, LED_WHITE)
            self._led_state[note] = LED_WHITE

            # do the action
            try:
                action()
            except Exception:
                pass

            # restore fixed color
            self.schedule_message(
                MOMENTARY_FLASH_TICKS,
                lambda nn=note: self._restore_fixed_led(nn)
            )

        btn.add_value_listener(_handler, identify_sender=False)
        self._control_buttons.append(btn)

    def _make_control_listeners(self):
        # Track STOP (yellow)
        for i, note in enumerate(TRACK_STOP_NOTES):
            self._register_momentary_action(
                note=note,
                fixed_vel=LED_YELLOW,
                action=lambda idx=i: self._stop_track(idx),
                name="TrackStop_%d" % i,
            )

        # Track MUTE (purple)
        for i, note in enumerate(TRACK_MUTE_NOTES):
            self._register_momentary_action(
                note=note,
                fixed_vel=LED_PURPLE,
                action=lambda idx=i: self._toggle_mute(idx),
                name="TrackMute_%d" % i,
            )

        # Navigation (green) - move by 1 step
        self._register_momentary_action(NAV_NOTES["left"],  LED_GREEN, lambda: self._move_grid(-1, 0), "NavLeft")
        self._register_momentary_action(NAV_NOTES["right"], LED_GREEN, lambda: self._move_grid(+1, 0), "NavRight")
        self._register_momentary_action(NAV_NOTES["up"],    LED_GREEN, lambda: self._move_grid(0, -1), "NavUp")
        self._register_momentary_action(NAV_NOTES["down"],  LED_GREEN, lambda: self._move_grid(0, +1), "NavDown")

        # Track select (blue)
        self._register_momentary_action(TRACK_SELECT_NOTES["left"],  LED_BLUE, self._select_prev_track, "TrackPrev")
        self._register_momentary_action(TRACK_SELECT_NOTES["right"], LED_BLUE, self._select_next_track, "TrackNext")

        # Transport (play blue, stop red)
        self._register_momentary_action(TRANSPORT_NOTES["play"], LED_BLUE, self._transport_play, "MasterPlay")
        self._register_momentary_action(TRANSPORT_NOTES["stop"], LED_RED,  self._transport_stop, "MasterStop")

        # Scene select/play (left/right pink, play blue)
        self._register_momentary_action(SCENE_NOTES["left"],  LED_PINK, self._select_prev_scene, "ScenePrev")
        self._register_momentary_action(SCENE_NOTES["right"], LED_PINK, self._select_next_scene, "SceneNext")
        self._register_momentary_action(SCENE_NOTES["play"],  LED_BLUE, self._play_selected_scene, "ScenePlay")

    # -------------------------
    # Actions
    # -------------------------
    def _stop_track(self, grid_track_index):
        try:
            song = self.song
            t = int(self._track_offset) + int(grid_track_index)
            if 0 <= t < len(song.tracks):
                song.tracks[t].stop_all_clips()
        except Exception:
            pass

    def _toggle_mute(self, grid_track_index):
        try:
            song = self.song
            t = int(self._track_offset) + int(grid_track_index)
            if 0 <= t < len(song.tracks):
                track = song.tracks[t]
                track.mute = not bool(track.mute)
        except Exception:
            pass

    def _move_grid(self, d_tracks, d_scenes):
        song = self.song
        max_track_offset = max(0, len(song.tracks) - GRID_TRACKS)
        max_scene_offset = max(0, len(song.scenes) - GRID_SCENES)

        self._track_offset = min(max_track_offset, max(0, self._track_offset + int(d_tracks)))
        self._scene_offset = min(max_scene_offset, max(0, self._scene_offset + int(d_scenes)))

        self._update_red_box()
        # Refresh clip LEDs immediately so it feels responsive
        self._refresh_leds()

    def _transport_play(self):
        try:
            self.song.start_playing()
        except Exception:
            pass

    def _transport_stop(self):
        try:
            self.song.stop_playing()
        except Exception:
            pass

    def _select_prev_track(self):
        try:
            song = self.song
            tracks = list(song.tracks)
            cur = song.view.selected_track
            if cur in tracks:
                i = tracks.index(cur)
                song.view.selected_track = tracks[max(0, i - 1)]
        except Exception:
            pass

    def _select_next_track(self):
        try:
            song = self.song
            tracks = list(song.tracks)
            cur = song.view.selected_track
            if cur in tracks:
                i = tracks.index(cur)
                song.view.selected_track = tracks[min(len(tracks) - 1, i + 1)]
        except Exception:
            pass

    def _select_prev_scene(self):
        try:
            song = self.song
            scenes = list(song.scenes)
            cur = song.view.selected_scene
            if cur in scenes:
                i = scenes.index(cur)
                song.view.selected_scene = scenes[max(0, i - 1)]
        except Exception:
            pass

    def _select_next_scene(self):
        try:
            song = self.song
            scenes = list(song.scenes)
            cur = song.view.selected_scene
            if cur in scenes:
                i = scenes.index(cur)
                song.view.selected_scene = scenes[min(len(scenes) - 1, i + 1)]
        except Exception:
            pass

    def _play_selected_scene(self):
        try:
            scene = self.song.view.selected_scene
            if scene is not None:
                scene.fire()
        except Exception:
            pass

    # -------------------------
    # LED refresh loop (polling) - CLIPS ONLY
    # -------------------------
    def _schedule_led_refresh(self):
        self.schedule_message(10, self._refresh_leds_and_reschedule)

    def _refresh_leds_and_reschedule(self):
        self._refresh_leds()
        self._schedule_led_refresh()

    def _refresh_leds(self):
        """
        Policy (your existing clip logic):
        - Empty slot: off (0)
        - Has clip: show clip color (palette id)
        - Playing/triggered: show brighter version
        """
        desired = {}

        for scene_index in range(GRID_SCENES):
            for track_index in range(GRID_TRACKS):
                slot = self._get_slot(track_index, scene_index)
                note = note_for_position(scene_index, track_index)

                vel = 0
                if slot is not None:
                    has_clip = bool(_safe_get(slot, "has_clip", False))
                    playing = bool(_safe_get(slot, "is_playing", False))
                    triggered = bool(_safe_get(slot, "is_triggered", False))

                    if has_clip:
                        clip = _safe_get(slot, "clip", None)

                        # Live clip color is usually clip.color (RGB int). If missing, fallback to color_index.
                        rgb_int = _safe_get(clip, "color", None) if clip else None
                        color_id = palette_color_id_from_live_rgb(rgb_int)

                        # Use palette id as velocity
                        vel = int(color_id) & 0x7F

                        # If playing/triggered, push it brighter without destroying hue too much.
                        if playing or triggered:
                            vel = min(127, vel + 30) if vel < 97 else 127

                desired[int(note)] = int(vel) & 0x7F

        for note, vel in desired.items():
            # Never override fixed pads
            if note in self._fixed_leds:
                continue

            if self._led_state.get(note) != vel:
                self._send_note(note, vel)
                self._led_state[note] = vel

    # -------------------------
    # MIDI OUT helpers (compat)
    # -------------------------
    def _send_note(self, note, velocity):
        status = 0x90 | (self._channel & 0x0F)  # NoteOn ch1
        msg = (status, int(note) & 0x7F, int(velocity) & 0x7F)

        if hasattr(self, "send_midi"):
            self.send_midi(msg)
        else:
            self._send_midi(msg)

    # -------------------------
    # Slot lookup (OFFSET-AWARE)
    # -------------------------
    def _get_slot(self, track_index, scene_index):
        song = self.song  # property in your Live build

        track_index = int(track_index) + int(self._track_offset)
        scene_index = int(scene_index) + int(self._scene_offset)

        if track_index < 0 or scene_index < 0:
            return None
        if track_index >= len(song.tracks) or scene_index >= len(song.scenes):
            return None

        track = song.tracks[track_index]
        if not hasattr(track, "clip_slots"):
            return None
        if scene_index >= len(track.clip_slots):
            return None

        return track.clip_slots[scene_index]
