from __future__ import absolute_import, print_function, unicode_literals

from ableton.v2.control_surface import ControlSurface
from ableton.v2.control_surface.elements import ButtonElement

MIDI_NOTE_TYPE = 0  # NOTE messages


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
        self.show_message("Mystrix_Pro loaded (Ableton palette colors)")

        with self.component_guard():
            self._channel = 0  # MIDI ch 1 (0-based)
            self._pad_buttons = []
            self._led_state = {}  # note -> last velocity sent

            self._make_pad_listeners()
            self._schedule_led_refresh()

    # -------------------------
    # Pads + launching
    # -------------------------
    def _make_pad_listeners(self):
        for scene_index in range(8):
            for track_index in range(8):
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
    # LED refresh loop (polling)
    # -------------------------
    def _schedule_led_refresh(self):
        self.schedule_message(10, self._refresh_leds_and_reschedule)

    def _refresh_leds_and_reschedule(self):
        self._refresh_leds()
        self._schedule_led_refresh()

    def _refresh_leds(self):
        """
        Policy:
        - Empty slot: off (0)
        - Has clip: show clip color (palette id)
        - Playing/triggered: show brighter version (we bias toward 127 if palette id is very dim)
        """
        desired = {}

        for scene_index in range(8):
            for track_index in range(8):
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
                            # If already bright, keep; else bump by a fixed amount capped at 127.
                            vel = min(127, vel + 30) if vel < 97 else 127

                desired[note] = vel

        for note, vel in desired.items():
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
    # Slot lookup
    # -------------------------
    def _get_slot(self, track_index, scene_index):
        song = self.song  # property in your Live build

        if track_index >= len(song.tracks) or scene_index >= len(song.scenes):
            return None

        track = song.tracks[track_index]
        if not hasattr(track, "clip_slots"):
            return None
        if scene_index >= len(track.clip_slots):
            return None

        return track.clip_slots[scene_index]
