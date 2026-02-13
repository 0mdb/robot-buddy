#!/usr/bin/env python3
"""Face simulator — renders a single 16×16 LED panel in a pygame window.

Both eyes share one panel.

Controls:
  Arrow keys     Shift gaze (hold)
  Space          Trigger blink
  1              Mood: DEFAULT
  2              Mood: TIRED
  3              Mood: ANGRY
  4              Mood: HAPPY
  C              Trigger confused animation
  L              Trigger laugh animation
  W              Wink left
  E              Wink right
  I              Toggle idle gaze wander
  B              Toggle auto-blink
  S              Toggle solid-eye mode (EVE/Astro style)
  +/-            Brightness up/down
  5              Trigger surprise
  6              Trigger heart eyes
  7              Trigger X eyes
  9              Trigger RAGE (fiery red eyes)
  8              Trigger sleepy drift
  G              Toggle edge glow
  K              Toggle sparkle
  F              Toggle afterglow
  R              Toggle breathing
  T              Toggle color emotion
  M              Toggle mouth
  0              Replay boot-up sequence
  F1             System: boot animation
  F2             System: error warning
  F3             System: low battery
  F4             System: updating/loading
  F5             System: shutting down
  F6             Clear system mode (back to face)
  Q / Esc        Quit
"""

from __future__ import annotations

import sys
import pygame

from face_state import (
    FaceState, Mood, Gesture, SystemMode,
    face_state_update, face_set_mood, face_set_gaze,
    face_blink, face_wink_left, face_wink_right,
    face_trigger_gesture, face_set_system_mode, GRID_SIZE,
)
from face_render import render_face

# ── Display constants ────────────────────────────────────────────────

PIXEL_SCALE = 28          # each LED pixel drawn as NxN screen pixels

PANEL_W = GRID_SIZE * PIXEL_SCALE
PANEL_H = GRID_SIZE * PIXEL_SCALE
WINDOW_W = PANEL_W + 40   # some padding
WINDOW_H = PANEL_H + 120  # extra room for HUD text

FPS = 60
BG = (20, 20, 25)


def draw_grid(surface: pygame.Surface, grid: list[list[tuple[int, int, int]]],
              ox: int, oy: int) -> None:
    """Draw a 16x16 LED grid onto the surface at offset (ox, oy)."""
    for y, row in enumerate(grid):
        for x, (r, g, b) in enumerate(row):
            rect = pygame.Rect(
                ox + x * PIXEL_SCALE + 1,
                oy + y * PIXEL_SCALE + 1,
                PIXEL_SCALE - 2,
                PIXEL_SCALE - 2,
            )
            pygame.draw.rect(surface, (r, g, b), rect, border_radius=4)


def main() -> None:
    pygame.init()
    screen = pygame.display.set_mode((WINDOW_W, WINDOW_H))
    pygame.display.set_caption("Robot Buddy — Face Simulator (16x16)")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("monospace", 14)

    fs = FaceState()
    fs.anim.autoblink = True
    fs.anim.idle = True

    manual_gaze = False

    running = True
    while running:
        # ── Events ───────────────────────────────────────────────────
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_q, pygame.K_ESCAPE):
                    running = False
                elif event.key == pygame.K_SPACE:
                    face_blink(fs)
                elif event.key == pygame.K_1:
                    face_set_mood(fs, Mood.DEFAULT)
                elif event.key == pygame.K_2:
                    face_set_mood(fs, Mood.TIRED)
                elif event.key == pygame.K_3:
                    face_set_mood(fs, Mood.ANGRY)
                elif event.key == pygame.K_4:
                    face_set_mood(fs, Mood.HAPPY)
                elif event.key == pygame.K_5:
                    face_trigger_gesture(fs, Gesture.SURPRISE)
                elif event.key == pygame.K_6:
                    face_trigger_gesture(fs, Gesture.HEART)
                elif event.key == pygame.K_7:
                    face_trigger_gesture(fs, Gesture.X_EYES)
                elif event.key == pygame.K_8:
                    face_trigger_gesture(fs, Gesture.SLEEPY)
                elif event.key == pygame.K_9:
                    face_trigger_gesture(fs, Gesture.RAGE)
                elif event.key == pygame.K_c:
                    face_trigger_gesture(fs, Gesture.CONFUSED)
                elif event.key == pygame.K_l:
                    face_trigger_gesture(fs, Gesture.LAUGH)
                elif event.key == pygame.K_w:
                    face_wink_left(fs)
                elif event.key == pygame.K_e:
                    face_wink_right(fs)
                elif event.key == pygame.K_i:
                    fs.anim.idle = not fs.anim.idle
                elif event.key == pygame.K_b:
                    fs.anim.autoblink = not fs.anim.autoblink
                elif event.key in (pygame.K_EQUALS, pygame.K_PLUS):
                    fs.brightness = min(1.0, fs.brightness + 0.1)
                elif event.key == pygame.K_MINUS:
                    fs.brightness = max(0.1, fs.brightness - 0.1)
                elif event.key == pygame.K_s:
                    fs.solid_eye = not fs.solid_eye
                elif event.key == pygame.K_g:
                    fs.fx.edge_glow = not fs.fx.edge_glow
                elif event.key == pygame.K_k:
                    fs.fx.sparkle = not fs.fx.sparkle
                elif event.key == pygame.K_f:
                    fs.fx.afterglow = not fs.fx.afterglow
                elif event.key == pygame.K_r:
                    fs.fx.breathing = not fs.fx.breathing
                elif event.key == pygame.K_t:
                    fs.fx.color_emotion = not fs.fx.color_emotion
                elif event.key == pygame.K_m:
                    fs.mouth = not fs.mouth
                elif event.key == pygame.K_0:
                    # Replay boot-up sequence
                    fs.fx.boot_active = True
                    fs.fx.boot_phase = 0
                    fs.fx.boot_timer = 0.0
                    fs.eye_l.openness = 0.0
                    fs.eye_r.openness = 0.0
                # ── System mode keys (F1-F5) ────────────
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

        # ── Held keys → manual gaze ─────────────────────────────────
        keys = pygame.key.get_pressed()
        gx, gy = 0.0, 0.0
        if keys[pygame.K_LEFT]:
            gx -= 3.0
        if keys[pygame.K_RIGHT]:
            gx += 3.0
        if keys[pygame.K_UP]:
            gy -= 2.0
        if keys[pygame.K_DOWN]:
            gy += 2.0

        if gx != 0.0 or gy != 0.0:
            face_set_gaze(fs, gx, gy)
            manual_gaze = True
        elif manual_gaze:
            face_set_gaze(fs, 0, 0)
            manual_gaze = False

        # ── Update state machine ─────────────────────────────────────
        face_state_update(fs)

        # ── Render ───────────────────────────────────────────────────
        grid = render_face(fs)

        screen.fill(BG)

        # Center the panel
        ox = (WINDOW_W - PANEL_W) // 2
        oy = 10
        draw_grid(screen, grid, ox, oy)

        # ── HUD ──────────────────────────────────────────────────────
        hud_y = PANEL_H + 20
        mood_name = fs.mood.name
        idle_str = "ON" if fs.anim.idle else "OFF"
        blink_str = "ON" if fs.anim.autoblink else "OFF"
        style_str = "SOLID" if fs.solid_eye else "PUPIL"
        hud = (
            f"Mood: {mood_name}  |  Style: {style_str}  |  Idle: {idle_str}"
            f"  |  Blink: {blink_str}  |  Bright: {fs.brightness:.1f}"
        )
        text_surf = font.render(hud, True, (160, 160, 170))
        screen.blit(text_surf, (10, hud_y))

        # FX status line
        glow_str = "ON" if fs.fx.edge_glow else "OFF"
        sparkle_str = "ON" if fs.fx.sparkle else "OFF"
        afterglow_str = "ON" if fs.fx.afterglow else "OFF"
        breath_str = "ON" if fs.fx.breathing else "OFF"
        color_str = "ON" if fs.fx.color_emotion else "OFF"
        fx_hud = (
            f"Glow: {glow_str}  |  Sparkle: {sparkle_str}  |  Afterglow: {afterglow_str}"
            f"  |  Breath: {breath_str}  |  Color: {color_str}"
        )
        fx_surf = font.render(fx_hud, True, (130, 140, 150))
        screen.blit(fx_surf, (10, hud_y + 18))

        controls1 = "Spc:blink 1-4:mood 5:surprise 6:heart 7:x-eyes 8:sleepy 9:RAGE 0:boot"
        ctrl_surf1 = font.render(controls1, True, (90, 90, 100))
        screen.blit(ctrl_surf1, (10, hud_y + 38))

        controls2 = "C:confused L:laugh W/E:wink S:style G:glow K:sparkle F:afterglow R:breath T:color M:mouth"
        ctrl_surf2 = font.render(controls2, True, (90, 90, 100))
        screen.blit(ctrl_surf2, (10, hud_y + 56))

        sys_mode_name = fs.system.mode.name if fs.system.mode != SystemMode.NONE else ""
        controls3 = "F1:boot F2:error F3:battery F4:update F5:shutdown F6:clear"
        if sys_mode_name:
            controls3 = f"[{sys_mode_name}]  " + controls3
        ctrl_surf3 = font.render(controls3, True, (90, 90, 100))
        screen.blit(ctrl_surf3, (10, hud_y + 74))

        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
