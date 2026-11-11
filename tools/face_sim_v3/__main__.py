"""Face Simulator V3 — pixel-accurate 320x240 spec implementation.

Run: python -m face_sim_v3  (from tools/)
     just sim              (from repo root)
"""

from __future__ import annotations

import sys
import time

import pygame

from tools.face_sim_v3.debug.overlay import DebugOverlay
from tools.face_sim_v3.debug.timeline import Timeline
from tools.face_sim_v3.input.command_bus import (
    CommandBus,
    SetConvStateCmd,
    SetStateCmd,
)
from tools.face_sim_v3.input.keyboard import KeyboardHandler
from tools.face_sim_v3.input.touch import TouchClassifier, TouchGesture
from tools.face_sim_v3.render.border import BorderRenderer
from tools.face_sim_v3.render.face import render_face
from tools.face_sim_v3.render.touch_ring import TouchRing
from tools.face_sim_v3.state.constants import (
    ANIM_FPS,
    BG_COLOR,
    CONV_FLAGS,
    CONV_GAZE,
    ConvState,
    ERROR_AVERSION_DURATION,
    ERROR_AVERSION_GAZE_X,
    GestureId,
    MAX_GAZE,
    PIXEL_SCALE,
    SCREEN_H,
    SCREEN_W,
    SystemMode,
    TOUCH_GAZE_FOLLOW,
    TOUCH_RING_COLOR_START,
    TOUCH_RING_COLOR_STOP,
)
from tools.face_sim_v3.state.conv_choreographer import ConvTransitionChoreographer
from tools.face_sim_v3.state.conv_state import ConvStateMachine
from tools.face_sim_v3.state.face_state import (
    FaceState,
    face_set_flags,
    face_pet,
    face_set_gaze,
    face_state_update,
    face_trigger_gesture,
)
from tools.face_sim_v3.state.guardrails import Guardrails
from tools.face_sim_v3.state.mood_sequencer import MoodSequencer

# ── Display constants ────────────────────────────────────────────────

CANVAS_W = SCREEN_W * PIXEL_SCALE  # 640
CANVAS_H = SCREEN_H * PIXEL_SCALE  # 480
LED_SIZE = 16
LED_MARGIN = 12
WINDOW_W = CANVAS_W + 40
WINDOW_H = CANVAS_H + 200  # Room for LED + HUD + timeline
WINDOW_BG = (20, 20, 25)
CANVAS_OX = (WINDOW_W - CANVAS_W) // 2  # canvas top-left in the window
CANVAS_OY = 10

# Conversation states in which a tap cancels the session (spec §9.5)
_TAP_CANCEL_STATES = (
    ConvState.ATTENTION,
    ConvState.LISTENING,
    ConvState.THINKING,
    ConvState.SPEAKING,
    ConvState.ERROR,
)


# ── Drawing helpers ──────────────────────────────────────────────────


def _draw_canvas(
    surface: pygame.Surface, buf: list[tuple[int, int, int]], ox: int, oy: int
) -> None:
    """Draw the 320x240 pixel buffer scaled up onto the pygame surface."""
    for y in range(SCREEN_H):
        row_offset = y * SCREEN_W
        for x in range(SCREEN_W):
            r, g, b = buf[row_offset + x]
            if (r, g, b) == BG_COLOR:
                continue
            rect = pygame.Rect(
                ox + x * PIXEL_SCALE,
                oy + y * PIXEL_SCALE,
                PIXEL_SCALE,
                PIXEL_SCALE,
            )
            pygame.draw.rect(surface, (r, g, b), rect)


def _draw_led(
    surface: pygame.Surface, color: tuple[int, int, int], x: int, y: int
) -> None:
    """Draw the simulated WS2812B LED indicator."""
    if any(c > 5 for c in color):
        glow = pygame.Surface((LED_SIZE * 3, LED_SIZE * 3), pygame.SRCALPHA)
        gc = (*color, 40)
        pygame.draw.circle(
            glow, gc, (LED_SIZE * 3 // 2, LED_SIZE * 3 // 2), LED_SIZE * 3 // 2
        )
        surface.blit(glow, (x - LED_SIZE, y - LED_SIZE))
    pygame.draw.circle(surface, color, (x, y), LED_SIZE // 2)
    pygame.draw.circle(surface, (60, 60, 65), (x, y), LED_SIZE // 2, 1)


def _window_to_screen(wx: int, wy: int) -> tuple[int, int, bool]:
    """Map window coords to 320x240 screen coords (clamped) + inside flag."""
    sx = (wx - CANVAS_OX) // PIXEL_SCALE
    sy = (wy - CANVAS_OY) // PIXEL_SCALE
    inside = 0 <= sx < SCREEN_W and 0 <= sy < SCREEN_H
    return (
        max(0, min(SCREEN_W - 1, sx)),
        max(0, min(SCREEN_H - 1, sy)),
        inside,
    )


# ── Touch (mouse = finger) ───────────────────────────────────────────


class SimTouch:
    """Mouse-as-touch: gesture classification + local MCU-style feedback.

    Local feedback mirrors the face firmware (spec §9.5): gaze follows the
    finger, long-press ring, boop blink on tap while IDLE, content look while
    stroking. All of it is
    suppressed while a system overlay is active (spec §4.4).
    """

    def __init__(self) -> None:
        self.clf = TouchClassifier()
        self.pending: list[TouchGesture] = []
        self.last: str = ""
        self._saved_gaze: tuple[float, float, float, float] | None = None
        self._flash_color: tuple[int, int, int] = TOUCH_RING_COLOR_START

    def handle_event(self, event: pygame.event.Event, fs: FaceState) -> None:
        now_ms = time.monotonic() * 1000.0
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            sx, sy, inside = _window_to_screen(*event.pos)
            if inside and fs.system.mode == SystemMode.NONE:
                self.clf.press(sx, sy, now_ms)
                self._saved_gaze = (
                    fs.eye_l.gaze_x_target,
                    fs.eye_l.gaze_y_target,
                    fs.eye_r.gaze_x_target,
                    fs.eye_r.gaze_y_target,
                )
        elif event.type == pygame.MOUSEMOTION and self.clf.active:
            sx, sy, _ = _window_to_screen(*event.pos)
            self._queue(self.clf.move(sx, sy, now_ms))
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if self.clf.active:
                sx, sy, _ = _window_to_screen(*event.pos)
                self._queue(self.clf.release(sx, sy, now_ms))
                self._restore_gaze(fs)

    def _queue(self, g: TouchGesture) -> None:
        if g != TouchGesture.NONE:
            self.pending.append(g)

    def _restore_gaze(self, fs: FaceState) -> None:
        if self._saved_gaze is None:
            return
        lx, ly, rx, ry = self._saved_gaze
        fs.eye_l.gaze_x_target, fs.eye_l.gaze_y_target = lx, ly
        fs.eye_r.gaze_x_target, fs.eye_r.gaze_y_target = rx, ry
        self._saved_gaze = None

    def update(
        self, fs: FaceState, conv_sm: ConvStateMachine, timeline: Timeline
    ) -> None:
        """Per-frame: fire long-press, run host mapping, apply gaze follow."""
        now_ms = time.monotonic() * 1000.0
        if fs.system.mode != SystemMode.NONE:
            if self.clf.active:
                self._restore_gaze(fs)
            self.clf.cancel()
            self.pending.clear()
            return

        self._queue(self.clf.update(now_ms))
        for g in self.pending:
            if g == TouchGesture.LONG_PRESS:
                # Latch the colour the ring showed while filling
                self._flash_color = self.ring_color(conv_sm)
            elif g == TouchGesture.TAP and conv_sm.state == ConvState.IDLE:
                face_trigger_gesture(fs, GestureId.BLINK)  # local boop
                timeline.log_gesture(GestureId.BLINK)
            self.last = g.name
            _host_on_touch_gesture(g, conv_sm)
        self.pending.clear()

        if self.clf.petting:
            face_pet(fs)  # local content look while stroking (MCU: face_pet)

        if self.clf.active and TOUCH_GAZE_FOLLOW:
            gx = (self.clf.x - SCREEN_W / 2) / (SCREEN_W / 2) * MAX_GAZE
            gy = (self.clf.y - SCREEN_H / 2) / (SCREEN_H / 2) * MAX_GAZE
            face_set_gaze(fs, gx, gy)
            # Hold off idle wander so it doesn't yank the eyes away
            fs.anim.next_idle = max(fs.anim.next_idle, time.monotonic() + 0.1)

    @staticmethod
    def ring_color(conv_sm: ConvStateMachine) -> tuple[int, int, int]:
        """Amber when long-press will start listening, white when it stops."""
        return TOUCH_RING_COLOR_STOP if conv_sm.ptt_on else TOUCH_RING_COLOR_START

    def ring(self, conv_sm: ConvStateMachine) -> TouchRing | None:
        now_ms = time.monotonic() * 1000.0
        flash = self.clf.ring_flash(now_ms)
        if flash is not None:
            return TouchRing(
                self.clf.flash_x, self.clf.flash_y, 1.0, self._flash_color, flash
            )
        progress = self.clf.ring_progress(now_ms)
        if progress is None:
            return None
        return TouchRing(self.clf.x, self.clf.y, progress, self.ring_color(conv_sm))

    def status(self) -> str:
        state = "down" if self.clf.active else "up"
        return f"{state} last={self.last or '-'}"


def _host_on_touch_gesture(g: TouchGesture, conv_sm: ConvStateMachine) -> None:
    """Stand-in for the supervisor tick loop's touch mapping (spec §9.5)."""
    if g == TouchGesture.LONG_PRESS:
        if conv_sm.ptt_on:
            conv_sm.set_state(ConvState.THINKING)  # end utterance
        else:
            conv_sm.ptt_held = True
            conv_sm.set_state(ConvState.ATTENTION)  # -> PTT after attention
    elif g == TouchGesture.TAP:
        if conv_sm.ptt_on:
            conv_sm.set_state(ConvState.THINKING)  # "I'm done talking"
        elif conv_sm.state in _TAP_CANCEL_STATES:
            conv_sm.set_state(ConvState.DONE)  # cancel the session
        # Outside a conversation: boop only (local), no host action


# ── Main loop ────────────────────────────────────────────────────────


def main() -> None:
    pygame.init()
    screen = pygame.display.set_mode((WINDOW_W, WINDOW_H))
    pygame.display.set_caption("Robot Buddy — Face Simulator V3")
    clock = pygame.time.Clock()

    # Core state
    fs = FaceState()
    conv_sm = ConvStateMachine()
    sequencer = MoodSequencer()
    guardrails = Guardrails()
    choreo = ConvTransitionChoreographer()

    # Input
    bus = CommandBus()
    keyboard = KeyboardHandler(bus)
    touch = SimTouch()

    # Rendering
    border = BorderRenderer()

    # Debug
    overlay = DebugOverlay()
    timeline = Timeline()

    # Track previous conv state for timeline logging + flag transitions
    prev_conv = conv_sm.state
    prev_mood = fs.mood
    prev_conv_for_flags = conv_sm.state  # Separate tracker for flag application

    running = True
    while running:
        frame_start = time.monotonic()
        dt = 1.0 / ANIM_FPS

        # ── 1. Handle pygame events → keyboard → command bus ─────
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                keyboard.handle_event(event, fs)
            elif event.type in (
                pygame.MOUSEBUTTONDOWN,
                pygame.MOUSEMOTION,
                pygame.MOUSEBUTTONUP,
            ):
                touch.handle_event(event, fs)

        if keyboard.quit_requested:
            running = False
            continue

        # ── 2. Handle held keys (gaze arrows) ───────────────────
        keys = pygame.key.get_pressed()
        keyboard.handle_held_keys(keys)

        # ── 3. Dispatch commands ─────────────────────────────────
        # Intercept mood commands for sequencer routing
        _dispatch_with_sequencer(bus, fs, conv_sm, sequencer)

        # ── 4. Apply conversation state effects ──────────────────
        conv_changed = conv_sm.state != prev_conv_for_flags
        _apply_conv_effects(
            conv_sm, fs, border, conv_changed, keyboard.manual_gaze, choreo
        )
        if conv_changed:
            prev_conv_for_flags = conv_sm.state

        # ── 4b. Touch gestures + local feedback (after conv gaze) ─
        touch.update(fs, conv_sm, timeline)

        # ── 5. Update conversation state machine ─────────────────
        conv_sm.update(dt)

        # ── 6. Update mood sequencer ─────────────────────────────
        sequencer.update(fs, dt)

        # ── 7. Check guardrails ──────────────────────────────────
        mood_out, intensity_out = guardrails.check(
            fs.mood,
            fs.expression_intensity,
            conv_sm.session_active,
        )
        if mood_out != fs.mood:
            timeline.log_guardrail(f"{fs.mood.name}→NEUTRAL")
            sequencer.request_mood(mood_out, intensity_out)
        elif intensity_out != fs.expression_intensity:
            sequencer.target_intensity = intensity_out

        # ── 8. Update face state (tweens, springs, effects) ──────
        face_state_update(fs)

        # ── 9. Update border renderer ────────────────────────────
        border.set_energy(fs.talking_energy)
        border.update(conv_sm.state, conv_sm.timer, dt)
        border.update_state_ref(conv_sm.state, conv_sm.timer)

        # ── 10. Transition choreography + timeline logging ──────
        if conv_sm.state != prev_conv:
            choreo.on_transition(prev_conv, conv_sm.state)
            timeline.log_conv(conv_sm.state)
            prev_conv = conv_sm.state

        # Advance choreographer and dispatch actions
        choreo_actions = choreo.update(dt * 1000.0)
        for action in choreo_actions:
            if action.kind == "gesture":
                gid = action.params.get("gesture_id")
                if gid is not None:
                    from tools.face_sim_v3.state.constants import GestureId as _GId

                    face_trigger_gesture(fs, _GId(gid))
            elif action.kind == "mood_nudge":
                from tools.face_sim_v3.state.constants import Mood as _Mood

                sequencer.request_mood(
                    _Mood(action.params["mood_id"]),
                    action.params["intensity"],
                )

        if fs.mood != prev_mood:
            timeline.log_mood(fs.mood)
            prev_mood = fs.mood

        # ── 11. Render ───────────────────────────────────────────
        buf = render_face(fs, border, touch.ring(conv_sm))

        screen.fill(WINDOW_BG)

        # Canvas (centered)
        ox, oy = CANVAS_OX, CANVAS_OY
        _draw_canvas(screen, buf, ox, oy)

        # LED indicator (top-right)
        led_x = ox + CANVAS_W + LED_MARGIN
        led_y = oy + LED_SIZE
        _draw_led(screen, border.led_color, led_x, led_y)

        # HUD overlay
        hud_y = CANVAS_H + 24
        overlay.frame_time_ms = (time.monotonic() - frame_start) * 1000.0
        overlay.render(
            surface=screen,
            y_offset=hud_y,
            fs=fs,
            conv_sm=conv_sm,
            border=border,
            sequencer=sequencer,
            guardrails=guardrails,
            touch_status=touch.status(),
        )

        # Timeline strip
        timeline_y = WINDOW_H - Timeline.STRIP_H - 6
        timeline.render(screen, 10, timeline_y, WINDOW_W - 20)

        # Window title with conv state
        conv_name = conv_sm.state.name
        pygame.display.set_caption(f"Robot Buddy — Face Sim V3  |  Conv: {conv_name}")

        pygame.display.flip()
        clock.tick(ANIM_FPS)

    pygame.quit()
    sys.exit()


# ── Integration helpers ──────────────────────────────────────────────


def _dispatch_with_sequencer(
    bus: CommandBus,
    fs: FaceState,
    conv_sm: ConvStateMachine,
    sequencer: MoodSequencer,
) -> None:
    """Dispatch commands, routing mood changes through the sequencer."""
    for cmd in bus._queue:
        if isinstance(cmd, SetStateCmd):
            if cmd.mood is not None:
                sequencer.request_mood(cmd.mood, cmd.intensity or 1.0)
                cmd.mood = None
                cmd.intensity = None
            if isinstance(cmd, SetConvStateCmd):
                if hasattr(conv_sm, "set_state"):
                    conv_sm.set_state(cmd.conv_state)
    bus.dispatch(fs, conv_sm)


def _apply_conv_effects(
    conv_sm: ConvStateMachine,
    fs: FaceState,
    border: BorderRenderer,
    conv_changed: bool,
    manual_gaze: bool,
    choreo: ConvTransitionChoreographer | None = None,
) -> None:
    """Apply per-state gaze overrides, mood hints, and flag changes.

    Flags are only applied on conversation state transitions (not every frame),
    matching real supervisor behavior where SET_FLAGS is sent once per transition.
    Gaze priority: choreographer ramp > conv_state override > manual/idle.
    """
    state = conv_sm.state

    # Gaze override — skip when user is controlling gaze with arrow keys
    if not manual_gaze:
        # Choreographer gaze ramp takes priority over static conv_state override
        choreo_gaze = choreo.get_gaze_override() if choreo else None
        if choreo_gaze is not None:
            face_set_gaze(fs, choreo_gaze[0] * MAX_GAZE, choreo_gaze[1] * MAX_GAZE)
        else:
            gaze = CONV_GAZE.get(state)
            if gaze is not None:
                face_set_gaze(fs, gaze[0] * 12.0, gaze[1] * 12.0)

        # Task 6: ERROR micro-aversion (spec §4.2.2) — brief leftward gaze
        if state == ConvState.ERROR and conv_sm.timer < ERROR_AVERSION_DURATION:
            face_set_gaze(fs, ERROR_AVERSION_GAZE_X * MAX_GAZE, 0.0)

    # Flag overrides — only on state transitions (matches supervisor protocol)
    if conv_changed:
        flags = CONV_FLAGS.get(state, -1)
        if flags != -1:
            face_set_flags(fs, flags)

    # Backchannel — NOD during LISTENING + interest escalation
    if conv_sm.nod_pending:
        from tools.face_sim_v3.state.constants import GestureId

        face_trigger_gesture(fs, GestureId.NOD)
        conv_sm.nod_pending = False

    if conv_sm.interest_scale > 1.001:
        fs.eye_l.width_scale_target = max(
            fs.eye_l.width_scale_target, conv_sm.interest_scale
        )
        fs.eye_r.width_scale_target = max(
            fs.eye_r.width_scale_target, conv_sm.interest_scale
        )


if __name__ == "__main__":
    main()
