#!/usr/bin/env python3
"""Face simulator v2 — renders 320x240 TFT face in landscape at 2x scale.

Targets the new 12-mood / 13-gesture expression system matching the
ESP32 face-display firmware.  Designs iterated here will be ported to
the firmware renderer (face_ui.cpp).

Controls:
  Arrow keys     Shift gaze (hold)
  Space          Trigger blink

  Moods (number keys):
  1  NEUTRAL       2  HAPPY        3  EXCITED      4  CURIOUS
  5  SAD           6  SCARED       7  ANGRY         8  SURPRISED
  9  SLEEPY        0  LOVE         -  SILLY         =  THINKING

  Gestures:
  C  Confused      L  Laugh        W  Wink left     E  Wink right
  H  Heart eyes    X  X eyes       Z  Sleepy drift   R  Rage
  N  Nod           D  Headshake    J  Wiggle

  Toggles:
  I  Idle gaze wander     B  Auto-blink
  S  Solid/pupil style    M  Mouth on/off
  T  Talking on/off       G  Edge glow
  K  Sparkle              F  Afterglow
  P  PTT button toggle

  Conversation states (F7-F12, Shift+F7-F8):
  F7  Attention    F8  Listening    F9  PTT       F10 Thinking
  F11 Speaking     F12 Error       Shift+F7 Done  Shift+F8 Idle

  System modes:
  F1 Boot    F2 Error    F3 Battery    F4 Updating    F5 Shutdown    F6 Clear

  +/-        Brightness up/down
  [ / ]      Talking energy down/up (while talking)
  Q / Esc    Quit
"""

from __future__ import annotations

import sys
import pygame

from face_state_v2 import (
    FaceState,
    Mood,
    Gesture,
    SystemMode,
    SCREEN_W,
    SCREEN_H,
    face_state_update,
    face_set_mood,
    face_set_gaze,
    face_blink,
    face_wink_left,
    face_wink_right,
    face_trigger_gesture,
    face_set_system_mode,
    MAX_GAZE,
)
from face_render_v2 import render_face, BG_COLOR
from conv_border import ConvBorder, ConvState, CONV_NAMES  # noqa: E402

# ── Display constants ────────────────────────────────────────────────

PIXEL_SCALE = 2
CANVAS_W = SCREEN_W * PIXEL_SCALE  # 640
CANVAS_H = SCREEN_H * PIXEL_SCALE  # 480
LED_SIZE = 16  # simulated WS2812B indicator
LED_MARGIN = 12
WINDOW_W = CANVAS_W + 40  # padding
WINDOW_H = CANVAS_H + 160  # room for HUD + LED

FPS = 30
BG = (20, 20, 25)

MOOD_NAMES = {m: m.name for m in Mood}


def draw_canvas(
    surface: pygame.Surface, buf: list[tuple[int, int, int]], ox: int, oy: int
) -> None:
    """Draw the 320x240 pixel buffer scaled up onto the pygame surface."""
    for y in range(SCREEN_H):
        row_offset = y * SCREEN_W
        for x in range(SCREEN_W):
            r, g, b = buf[row_offset + x]
            if (r, g, b) == BG_COLOR:
                continue  # skip background pixels
            rect = pygame.Rect(
                ox + x * PIXEL_SCALE,
                oy + y * PIXEL_SCALE,
                PIXEL_SCALE,
                PIXEL_SCALE,
            )
            pygame.draw.rect(surface, (r, g, b), rect)


def draw_led(
    surface: pygame.Surface, color: tuple[int, int, int], x: int, y: int
) -> None:
    """Draw the simulated WS2812B LED indicator."""
    # Glow halo
    if any(c > 5 for c in color):
        glow = pygame.Surface((LED_SIZE * 3, LED_SIZE * 3), pygame.SRCALPHA)
        gc = (*color, 40)
        pygame.draw.circle(
            glow, gc, (LED_SIZE * 3 // 2, LED_SIZE * 3 // 2), LED_SIZE * 3 // 2
        )
        surface.blit(glow, (x - LED_SIZE, y - LED_SIZE))
    # LED body
    pygame.draw.circle(surface, color, (x, y), LED_SIZE // 2)
    pygame.draw.circle(surface, (60, 60, 65), (x, y), LED_SIZE // 2, 1)


def main() -> None:
    pygame.init()
    screen = pygame.display.set_mode((WINDOW_W, WINDOW_H))
    pygame.display.set_caption("Robot Buddy — Face Simulator v2 (320x240 TFT)")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("monospace", 14)

    fs = FaceState()
    fs.anim.autoblink = True
    fs.anim.idle = True

    conv = ConvBorder()

    manual_gaze = False

    running = True
    while running:
        dt = 1.0 / FPS

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                shift = event.mod & pygame.KMOD_SHIFT

                if event.key in (pygame.K_q, pygame.K_ESCAPE):
                    running = False

                elif event.key == pygame.K_SPACE:
                    face_blink(fs)

                # ── Moods ──────────────────────────────────────
                elif event.key == pygame.K_1:
                    face_set_mood(fs, Mood.NEUTRAL)
                elif event.key == pygame.K_2:
                    face_set_mood(fs, Mood.HAPPY)
                elif event.key == pygame.K_3:
                    face_set_mood(fs, Mood.EXCITED)
                elif event.key == pygame.K_4:
                    face_set_mood(fs, Mood.CURIOUS)
                elif event.key == pygame.K_5:
                    face_set_mood(fs, Mood.SAD)
                elif event.key == pygame.K_6:
                    face_set_mood(fs, Mood.SCARED)
                elif event.key == pygame.K_7:
                    face_set_mood(fs, Mood.ANGRY)
                elif event.key == pygame.K_8:
                    face_set_mood(fs, Mood.SURPRISED)
                elif event.key == pygame.K_9:
                    face_set_mood(fs, Mood.SLEEPY)
                elif event.key == pygame.K_0:
                    face_set_mood(fs, Mood.LOVE)
                elif event.key == pygame.K_MINUS:
                    face_set_mood(fs, Mood.SILLY)
                elif event.key == pygame.K_EQUALS and not shift:
                    face_set_mood(fs, Mood.THINKING)

                # ── Gestures ───────────────────────────────────
                elif event.key == pygame.K_c:
                    face_trigger_gesture(fs, Gesture.CONFUSED)
                elif event.key == pygame.K_l:
                    face_trigger_gesture(fs, Gesture.LAUGH)
                elif event.key == pygame.K_w:
                    face_wink_left(fs)
                elif event.key == pygame.K_e:
                    face_wink_right(fs)
                elif event.key == pygame.K_h:
                    face_trigger_gesture(fs, Gesture.HEART)
                elif event.key == pygame.K_x:
                    face_trigger_gesture(fs, Gesture.X_EYES)
                elif event.key == pygame.K_z:
                    face_trigger_gesture(fs, Gesture.SLEEPY)
                elif event.key == pygame.K_r:
                    face_trigger_gesture(fs, Gesture.RAGE)
                elif event.key == pygame.K_n:
                    face_trigger_gesture(fs, Gesture.NOD)
                elif event.key == pygame.K_d:
                    face_trigger_gesture(fs, Gesture.HEADSHAKE)
                elif event.key == pygame.K_j:
                    face_trigger_gesture(fs, Gesture.WIGGLE)

                # ── Toggles ────────────────────────────────────
                elif event.key == pygame.K_i:
                    fs.anim.idle = not fs.anim.idle
                elif event.key == pygame.K_b:
                    fs.anim.autoblink = not fs.anim.autoblink
                elif event.key == pygame.K_s:
                    fs.solid_eye = not fs.solid_eye
                elif event.key == pygame.K_m:
                    fs.show_mouth = not fs.show_mouth
                elif event.key == pygame.K_t:
                    fs.talking = not fs.talking
                    if not fs.talking:
                        fs.talking_energy = 0.0
                    else:
                        fs.talking_energy = 0.5
                elif event.key == pygame.K_g:
                    fs.fx.edge_glow = not fs.fx.edge_glow
                elif event.key == pygame.K_k:
                    fs.fx.sparkle = not fs.fx.sparkle
                elif event.key == pygame.K_f:
                    fs.fx.afterglow = not fs.fx.afterglow
                elif event.key == pygame.K_p:
                    conv.ptt_active = not conv.ptt_active

                # ── Brightness ─────────────────────────────────
                elif event.key == pygame.K_PLUS or (
                    event.key == pygame.K_EQUALS and shift
                ):
                    fs.brightness = min(1.0, fs.brightness + 0.1)

                # ── Talking energy ─────────────────────────────
                elif event.key == pygame.K_LEFTBRACKET:
                    fs.talking_energy = max(0.0, fs.talking_energy - 0.1)
                elif event.key == pygame.K_RIGHTBRACKET:
                    fs.talking_energy = min(1.0, fs.talking_energy + 0.1)

                # ── Conversation states ────────────────────────
                elif event.key == pygame.K_F7:
                    if shift:
                        conv.set_state(ConvState.DONE)
                    else:
                        conv.set_state(ConvState.ATTENTION)
                elif event.key == pygame.K_F8:
                    if shift:
                        conv.set_state(ConvState.IDLE)
                    else:
                        conv.set_state(ConvState.LISTENING)
                elif event.key == pygame.K_F9:
                    conv.set_state(ConvState.PTT)
                elif event.key == pygame.K_F10:
                    conv.set_state(ConvState.THINKING)
                elif event.key == pygame.K_F11:
                    conv.set_state(ConvState.SPEAKING)
                elif event.key == pygame.K_F12:
                    conv.set_state(ConvState.ERROR)

                # ── System modes ───────────────────────────────
                elif event.key == pygame.K_F1:
                    face_set_system_mode(fs, SystemMode.BOOTING)
                elif event.key == pygame.K_F2:
                    face_set_system_mode(fs, SystemMode.ERROR)
                elif event.key == pygame.K_F3:
                    face_set_system_mode(fs, SystemMode.LOW_BATTERY, 0.1)
                elif event.key == pygame.K_F4:
                    face_set_system_mode(fs, SystemMode.UPDATING)
                elif event.key == pygame.K_F5:
                    face_set_system_mode(fs, SystemMode.SHUTTING_DOWN)
                elif event.key == pygame.K_F6:
                    face_set_system_mode(fs, SystemMode.NONE)

        # ── Held keys → manual gaze ──────────────────────────────
        keys = pygame.key.get_pressed()
        gx, gy = 0.0, 0.0
        if keys[pygame.K_LEFT]:
            gx -= MAX_GAZE
        if keys[pygame.K_RIGHT]:
            gx += MAX_GAZE
        if keys[pygame.K_UP]:
            gy -= MAX_GAZE * 0.7
        if keys[pygame.K_DOWN]:
            gy += MAX_GAZE * 0.7

        if gx != 0.0 or gy != 0.0:
            face_set_gaze(fs, gx, gy)
            manual_gaze = True
        elif manual_gaze:
            face_set_gaze(fs, 0, 0)
            manual_gaze = False

        # ── Update state machines ────────────────────────────────
        face_state_update(fs)
        conv.set_energy(fs.talking_energy)
        conv.update(dt)

        # ── Update window title with conv state ──────────────────
        conv_name = CONV_NAMES.get(conv.state, "?")
        pygame.display.set_caption(f"Robot Buddy — Face Sim v2  |  Conv: {conv_name}")

        # ── Render ───────────────────────────────────────────────
        buf = render_face(fs, conv)

        screen.fill(BG)

        # Center the canvas
        ox = (WINDOW_W - CANVAS_W) // 2
        oy = 10
        draw_canvas(screen, buf, ox, oy)

        # ── LED indicator (top-right, outside canvas) ────────────
        led_x = ox + CANVAS_W + LED_MARGIN
        led_y = oy + LED_SIZE
        draw_led(screen, conv.led_color, led_x, led_y)

        # ── HUD ──────────────────────────────────────────────────
        hud_y = CANVAS_H + 24

        mood_name = fs.mood.name
        idle_str = "ON" if fs.anim.idle else "OFF"
        blink_str = "ON" if fs.anim.autoblink else "OFF"
        style_str = "SOLID" if fs.solid_eye else "PUPIL"
        talk_str = f"TALK({fs.talking_energy:.1f})" if fs.talking else "off"
        ptt_str = "ON" if conv.ptt_active else "off"
        hud = (
            f"Mood: {mood_name}  |  Style: {style_str}  |  Idle: {idle_str}"
            f"  |  Blink: {blink_str}  |  Bright: {fs.brightness:.1f}"
            f"  |  Talk: {talk_str}  |  PTT: {ptt_str}"
        )
        text_surf = font.render(hud, True, (160, 160, 170))
        screen.blit(text_surf, (10, hud_y))

        # Conv state + FX status
        conv_col = conv.color if conv.alpha > 0.1 else (100, 100, 110)
        conv_hud = f"Conv: {conv_name} (a={conv.alpha:.2f})"
        glow_str = "ON" if fs.fx.edge_glow else "OFF"
        sparkle_str = "ON" if fs.fx.sparkle else "OFF"
        afterglow_str = "ON" if fs.fx.afterglow else "OFF"
        mouth_str = "ON" if fs.show_mouth else "OFF"
        fx_hud = (
            f"{conv_hud}  |  Glow: {glow_str}  |  Sparkle: {sparkle_str}"
            f"  |  Afterglow: {afterglow_str}  |  Mouth: {mouth_str}"
        )
        fx_surf = font.render(fx_hud, True, conv_col)
        screen.blit(fx_surf, (10, hud_y + 18))

        # Controls line 1: moods
        ctrl1 = "1:neutral 2:happy 3:excited 4:curious 5:sad 6:scared 7:angry 8:surprised 9:sleepy 0:love -:silly =:thinking"
        screen.blit(font.render(ctrl1, True, (90, 90, 100)), (10, hud_y + 38))

        # Controls line 2: gestures
        ctrl2 = "C:confused L:laugh W/E:wink H:heart X:x-eyes Z:sleepy R:rage N:nod D:headshake J:wiggle"
        screen.blit(font.render(ctrl2, True, (90, 90, 100)), (10, hud_y + 56))

        # Controls line 3: toggles
        sys_name = fs.system.mode.name if fs.system.mode != SystemMode.NONE else ""
        ctrl3 = "S:style I:idle B:blink M:mouth T:talk G:glow K:sparkle F:afterglow P:ptt [/]:energy"
        if sys_name:
            ctrl3 = f"[{sys_name}]  " + ctrl3
        screen.blit(font.render(ctrl3, True, (90, 90, 100)), (10, hud_y + 74))

        # Controls line 4: conv states + system
        ctrl4 = "F7:attention F8:listen F9:ptt F10:think F11:speak F12:error  Sh+F7:done Sh+F8:idle"
        screen.blit(font.render(ctrl4, True, (90, 90, 100)), (10, hud_y + 92))

        ctrl5 = "F1:boot F2:error F3:battery F4:update F5:shutdown F6:clear"
        screen.blit(font.render(ctrl5, True, (70, 70, 80)), (10, hud_y + 110))

        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
