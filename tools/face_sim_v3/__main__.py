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
from tools.face_sim_v3.render.border import BorderRenderer
from tools.face_sim_v3.render.face import render_face
from tools.face_sim_v3.state.constants import (
    ANIM_FPS,
    BG_COLOR,
    CONV_FLAGS,
    CONV_GAZE,
    ConvState,
    ERROR_AVERSION_DURATION,
    ERROR_AVERSION_GAZE_X,
    MAX_GAZE,
    PIXEL_SCALE,
    SCREEN_H,
    SCREEN_W,
)
from tools.face_sim_v3.state.conv_state import ConvStateMachine
from tools.face_sim_v3.state.face_state import (
    FaceState,
    face_blink,
    face_set_flags,
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

    # Input
    bus = CommandBus()
    keyboard = KeyboardHandler(bus)

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
        _apply_conv_effects(conv_sm, fs, border, conv_changed, keyboard.manual_gaze)
        if conv_changed:
            prev_conv_for_flags = conv_sm.state

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

        # ── 10. Log timeline events + transition choreography ────
        if conv_sm.state != prev_conv:
            # Task 5: THINKING→SPEAKING anticipation blink (spec §5.1.2)
            if prev_conv == ConvState.THINKING and conv_sm.state == ConvState.SPEAKING:
                face_blink(fs)
            timeline.log_conv(conv_sm.state)
            prev_conv = conv_sm.state
        if fs.mood != prev_mood:
            timeline.log_mood(fs.mood)
            prev_mood = fs.mood

        # ── 11. Render ───────────────────────────────────────────
        buf = render_face(fs, border)

        screen.fill(WINDOW_BG)

        # Canvas (centered)
        ox = (WINDOW_W - CANVAS_W) // 2
        oy = 10
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
) -> None:
    """Apply per-state gaze overrides, mood hints, and flag changes.

    Flags are only applied on conversation state transitions (not every frame),
    matching real supervisor behavior where SET_FLAGS is sent once per transition.
    Gaze overrides yield to manual arrow-key input for sim debugging.
    """
    state = conv_sm.state

    # Gaze override — skip when user is controlling gaze with arrow keys
    if not manual_gaze:
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

    # Drive corner button visuals from conversation state
    from tools.face_sim_v3.state.constants import (
        ButtonIcon,
        ButtonState,
        CONV_COLORS,
    )

    if state in (ConvState.PTT, ConvState.LISTENING):
        border.set_button_left(ButtonIcon.MIC, ButtonState.ACTIVE, CONV_COLORS[state])
        border.set_button_right(
            ButtonIcon.X_MARK, ButtonState.ACTIVE, CONV_COLORS[state]
        )
    elif state in (ConvState.THINKING, ConvState.SPEAKING):
        border.set_button_left(ButtonIcon.MIC, ButtonState.IDLE)
        border.set_button_right(
            ButtonIcon.X_MARK, ButtonState.ACTIVE, CONV_COLORS[state]
        )
    else:
        border.set_button_left(ButtonIcon.MIC, ButtonState.IDLE)
        border.set_button_right(ButtonIcon.X_MARK, ButtonState.IDLE)


if __name__ == "__main__":
    main()
