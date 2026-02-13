"""Face renderer: converts FaceState into a single 16x16 RGB pixel buffer.

Both eyes share one 16x16 WS2812 panel.  Layout:
  - Left eye  occupies roughly columns 0..6   (center ~3.5)
  - Gap       columns 7..8
  - Right eye occupies roughly columns 9..15  (center ~12.5)
  - Vertical center for both eyes is row 8

Each eye is ~6px wide × ~8px tall when fully open.

Output is a 16×16 list of (R, G, B) tuples, ready for the simulator
or for packing into a WS2812 byte stream.
"""

from __future__ import annotations

import math
import time
from face_state import (
    FaceState, SystemMode, GRID_SIZE,
    get_breath_scale, get_emotion_color,
)

# ── Colour palette ───────────────────────────────────────────────────

EYE_COLOR = (255, 255, 255)   # white sclera
PUPIL_COLOR = (30, 100, 220)  # blue pupil
BG_COLOR = (0, 0, 0)          # off

# ── Eye shape parameters (in pixels on the shared 16x16 grid) ───────

EYE_WIDTH = 6.0         # fully open eye width  (per eye)
EYE_HEIGHT = 6.0        # fully open eye height (shrunk from 8 for mouth room)
EYE_CORNER_R = 2.0      # corner radius for rounded rect
PUPIL_R = 1.5           # pupil radius (scaled down with eye)

# Eye centers on the shared grid (shifted up from row 8 to row 5.5)
LEFT_EYE_CX = 4.0
LEFT_EYE_CY = 5.5
RIGHT_EYE_CX = 12.0
RIGHT_EYE_CY = 5.5

# Gaze scaling factors (smaller grid = less room to move)
GAZE_EYE_SHIFT = 0.15     # how much the eye shape shifts with gaze
GAZE_PUPIL_SHIFT = 0.5    # how much the pupil shifts with gaze


# ── Geometry helpers ─────────────────────────────────────────────────

def _in_rounded_rect(px: float, py: float,
                     cx: float, cy: float,
                     hw: float, hh: float,
                     r: float) -> bool:
    """Test if pixel (px, py) is inside a rounded rectangle centered at (cx, cy)
    with half-width hw, half-height hh, and corner radius r."""
    if hw <= 0 or hh <= 0:
        return False
    r = min(r, hw, hh)
    dx = abs(px - cx)
    dy = abs(py - cy)
    if dx > hw or dy > hh:
        return False
    if dx <= hw - r or dy <= hh - r:
        return True
    corner_dx = dx - (hw - r)
    corner_dy = dy - (hh - r)
    return (corner_dx * corner_dx + corner_dy * corner_dy) <= r * r


def _in_circle(px: float, py: float, cx: float, cy: float, r: float) -> bool:
    dx = px - cx
    dy = py - cy
    return (dx * dx + dy * dy) <= r * r


def _dist_to_edge(px: float, py: float,
                  cx: float, cy: float,
                  hw: float, hh: float) -> float:
    """Approximate distance from pixel to the nearest edge of the bounding box.
    Returns 0 at the edge, larger values toward center."""
    dx = hw - abs(px - cx)
    dy = hh - abs(py - cy)
    return max(0.0, min(dx, dy))


# ── Special shape helpers ────────────────────────────────────────────

def _in_heart(px: float, py: float, cx: float, cy: float, size: float) -> bool:
    """Test if pixel is inside a heart shape centered at (cx, cy)."""
    # Normalize to unit coordinates
    x = (px - cx) / size
    # Flip y so heart points downward (screen y goes down, equation expects y-up)
    y = (cy - py) / size
    # Shift so the lobes are centered visually
    y = y + 0.3
    # Heart equation: (x^2 + y^2 - 1)^3 - x^2 * y^3 <= 0
    x2 = x * x
    y2 = y * y
    return (x2 + y2 - 1.0) ** 3 - x2 * (y ** 3) <= 0


def _in_x_shape(px: float, py: float, cx: float, cy: float,
                size: float, thickness: float = 0.8) -> bool:
    """Test if pixel is inside an X shape centered at (cx, cy)."""
    dx = abs(px - cx)
    dy = abs(py - cy)
    if dx > size or dy > size:
        return False
    # Both diagonals: since dx/dy are abs, abs(dx-dy) catches all four arms
    return abs(dx - dy) < thickness


# ── Eyelid mask helpers ──────────────────────────────────────────────

def _tired_mask(px: float, py: float, cx: float, top_y: float,
                hw: float, amount: float) -> bool:
    """Tired eyelid: droops from outer edges toward center."""
    if amount < 0.01:
        return False
    max_droop = 2.6 * amount
    dist_from_center = abs(px - cx)
    droop_at_x = max_droop * (dist_from_center / max(hw, 0.01))
    return py < top_y + droop_at_x


def _angry_mask_left(px: float, py: float, cx: float, top_y: float,
                     hw: float, amount: float) -> bool:
    """Angry eyelid for left eye: slopes down toward inner edge (right side)."""
    if amount < 0.01:
        return False
    max_droop = 2.6 * amount
    t = (px - (cx - hw)) / max(2 * hw, 0.01)  # 0=outer, 1=inner
    droop_at_x = max_droop * t
    return py < top_y + droop_at_x


def _angry_mask_right(px: float, py: float, cx: float, top_y: float,
                      hw: float, amount: float) -> bool:
    """Angry eyelid for right eye: slopes down toward inner edge (left side)."""
    if amount < 0.01:
        return False
    max_droop = 2.6 * amount
    t = (px - (cx - hw)) / max(2 * hw, 0.01)
    droop_at_x = max_droop * (1.0 - t)
    return py < top_y + droop_at_x


def _happy_mask(px: float, py: float, bottom_y: float,
                amount: float) -> bool:
    """Happy eyelid: cuts from the bottom."""
    if amount < 0.01:
        return False
    cutoff = bottom_y - 2.2 * amount
    return py > cutoff


# ── Single-eye render helper ─────────────────────────────────────────

def _render_eye_onto(
    grid: list[list[tuple[int, int, int]]],
    fs: FaceState,
    is_left: bool,
) -> None:
    """Render one eye directly onto the shared 16x16 grid (mutates in place)."""

    eye = fs.eye_l if is_left else fs.eye_r
    base_cx = LEFT_EYE_CX if is_left else RIGHT_EYE_CX
    base_cy = LEFT_EYE_CY if is_left else RIGHT_EYE_CY

    # Get dynamic color
    solid_color = get_emotion_color(fs)

    # Breathing scale
    breath = get_breath_scale(fs)

    open_frac = max(0.0, min(1.0, eye.openness))

    # Apply squash & stretch + breathing to dimensions
    w_scale = eye.width_scale * breath
    h_scale = eye.height_scale * breath

    half_w = (EYE_WIDTH / 2.0) * w_scale
    half_h = (EYE_HEIGHT / 2.0) * open_frac * h_scale
    corner_r = EYE_CORNER_R * min(1.0, open_frac * 2)

    # Gaze shifts
    cx = base_cx + eye.gaze_x * GAZE_EYE_SHIFT
    cy = base_cy + eye.gaze_y * GAZE_EYE_SHIFT
    pupil_cx = base_cx + eye.gaze_x * GAZE_PUPIL_SHIFT
    pupil_cy = base_cy + eye.gaze_y * GAZE_PUPIL_SHIFT

    top_y = cy - half_h
    bottom_y = cy + half_h
    br = max(0.0, min(1.0, fs.brightness))

    # Edge glow parameters
    edge_glow = fs.fx.edge_glow
    edge_falloff = fs.fx.edge_glow_falloff

    # Heart eyes override: draw heart shape instead of rounded rect
    if fs.anim.heart:
        heart_size = 2.2 * breath
        for y in range(GRID_SIZE):
            for x in range(GRID_SIZE):
                px = x + 0.5
                py = y + 0.5
                if _in_heart(px, py, base_cx, base_cy, heart_size):
                    r, g, b = solid_color
                    grid[y][x] = (int(r * br), int(g * br), int(b * br))
        return

    # X eyes override: big red X per eye
    if fs.anim.x_eyes:
        for y in range(GRID_SIZE):
            for x in range(GRID_SIZE):
                px = x + 0.5
                py = y + 0.5
                if _in_x_shape(px, py, base_cx, base_cy, 2.8):
                    r, g, b = solid_color
                    grid[y][x] = (int(r * br), int(g * br), int(b * br))
        return

    for y in range(GRID_SIZE):
        for x in range(GRID_SIZE):
            px = x + 0.5
            py = y + 0.5

            if not _in_rounded_rect(px, py, cx, cy, half_w, half_h, corner_r):
                continue

            # Eyelid masks
            if is_left:
                if _angry_mask_left(px, py, cx, top_y, half_w, fs.eyelids.angry):
                    continue
            else:
                if _angry_mask_right(px, py, cx, top_y, half_w, fs.eyelids.angry):
                    continue

            if _tired_mask(px, py, cx, top_y, half_w, fs.eyelids.tired):
                continue

            if _happy_mask(px, py, bottom_y, fs.eyelids.happy):
                continue

            # Solid mode: uniform color.  Normal mode: sclera + pupil.
            if fs.solid_eye:
                r, g, b = solid_color
            elif _in_circle(px, py, pupil_cx, pupil_cy, PUPIL_R):
                r, g, b = PUPIL_COLOR
            else:
                r, g, b = EYE_COLOR

            # Edge glow: dim pixels near the edges
            if edge_glow:
                dist = _dist_to_edge(px, py, cx, cy, half_w, half_h)
                max_dist = min(half_w, half_h)
                if max_dist > 0:
                    glow = 1.0 - edge_falloff * (1.0 - min(dist / max_dist, 1.0))
                    r = int(r * glow)
                    g = int(g * glow)
                    b = int(b * glow)

            grid[y][x] = (int(r * br), int(g * br), int(b * br))


# ── Sparkle overlay ──────────────────────────────────────────────────

def _apply_sparkle(grid: list[list[tuple[int, int, int]]],
                   fs: FaceState) -> None:
    """Add sparkle pixels: brief bright white twinkles on lit pixels."""
    if not fs.fx.sparkle:
        return
    for sx, sy, life in fs.fx.sparkle_pixels:
        if 0 <= sx < GRID_SIZE and 0 <= sy < GRID_SIZE:
            existing = grid[sy][sx]
            # Only sparkle on lit pixels
            if existing != BG_COLOR:
                # Brightness based on remaining life
                intensity = min(1.0, life / 6.0)
                r = min(255, int(existing[0] + 80 * intensity))
                g = min(255, int(existing[1] + 80 * intensity))
                b = min(255, int(existing[2] + 80 * intensity))
                grid[sy][sx] = (r, g, b)


# ── Fire particles ───────────────────────────────────────────────────

def _apply_fire(grid: list[list[tuple[int, int, int]]],
                fs: FaceState) -> None:
    """Draw fire particles: red/orange/yellow pixels rising above the eyes."""
    if not fs.anim.rage:
        return
    for fx, fy, life, heat in fs.fx.fire_pixels:
        ix = int(fx)
        iy = int(fy)
        if 0 <= ix < GRID_SIZE and 0 <= iy < GRID_SIZE:
            # Color gradient: white-hot → yellow → orange → red → dim red
            if heat > 0.85:
                r, g, b = 255, 220, 120   # yellow-white core
            elif heat > 0.65:
                r, g, b = 255, 140, 20    # orange
            elif heat > 0.4:
                r, g, b = 220, 50, 0      # red-orange
            else:
                r, g, b = 130, 20, 0      # dim ember
            # Fade with remaining life
            fade = min(1.0, life / 5.0)
            grid[iy][ix] = (
                min(255, max(grid[iy][ix][0], int(r * fade))),
                min(255, max(grid[iy][ix][1], int(g * fade))),
                min(255, max(grid[iy][ix][2], int(b * fade))),
            )


# ── Afterglow ────────────────────────────────────────────────────────

def _apply_afterglow(grid: list[list[tuple[int, int, int]]],
                     fs: FaceState) -> None:
    """Blend current frame with previous frame for a soft fade-out effect."""
    if not fs.fx.afterglow or fs.fx.afterglow_grid is None:
        return
    prev = fs.fx.afterglow_grid
    decay = 0.4  # how much of the previous frame bleeds through
    for y in range(GRID_SIZE):
        for x in range(GRID_SIZE):
            cr, cg, cb = grid[y][x]
            pr, pg, pb = prev[y][x]
            # If current pixel is off but previous was on, show afterglow
            if cr == 0 and cg == 0 and cb == 0 and (pr > 0 or pg > 0 or pb > 0):
                grid[y][x] = (
                    int(pr * decay),
                    int(pg * decay),
                    int(pb * decay),
                )


# ── System mode renderers ────────────────────────────────────────────

_CENTER = GRID_SIZE / 2.0  # 8.0


def _render_system_booting(grid: list[list[tuple[int, int, int]]],
                           fs: FaceState) -> None:
    """Boot animation: expanding ring pulse from center, three waves,
    ending with a brief full-grid flash."""
    elapsed = time.monotonic() - fs.system.timer
    br = max(0.0, min(1.0, fs.brightness))

    # Three concentric ring waves, each 1s apart, expanding outward
    for wave in range(3):
        wave_start = wave * 0.4
        wave_elapsed = elapsed - wave_start
        if wave_elapsed < 0 or wave_elapsed > 1.5:
            continue
        # Ring expands from 0 to ~12 pixel radius over 1.5s
        radius = (wave_elapsed / 1.5) * 12.0
        thickness = 1.5
        # Fade out as it expands
        alpha = max(0.0, 1.0 - wave_elapsed / 1.5)

        for y in range(GRID_SIZE):
            for x in range(GRID_SIZE):
                dx = (x + 0.5) - _CENTER
                dy = (y + 0.5) - _CENTER
                dist = math.sqrt(dx * dx + dy * dy)
                if abs(dist - radius) < thickness:
                    intensity = alpha * (1.0 - abs(dist - radius) / thickness)
                    r = int(30 * intensity * br)
                    g = int(140 * intensity * br)
                    b = int(255 * intensity * br)
                    # Additive blend
                    cr, cg, cb = grid[y][x]
                    grid[y][x] = (min(255, cr + r), min(255, cg + g), min(255, cb + b))

    # Brief full-flash at the end (2.4s..2.7s) then fade
    if elapsed > 2.4:
        flash_t = min(1.0, (elapsed - 2.4) / 0.3)
        flash_alpha = 1.0 - flash_t  # fade out
        for y in range(GRID_SIZE):
            for x in range(GRID_SIZE):
                r = int(30 * flash_alpha * br)
                g = int(120 * flash_alpha * br)
                b = int(255 * flash_alpha * br)
                cr, cg, cb = grid[y][x]
                grid[y][x] = (min(255, cr + r), min(255, cg + g), min(255, cb + b))


def _render_system_error(grid: list[list[tuple[int, int, int]]],
                         fs: FaceState) -> None:
    """Error state: flashing warning triangle with exclamation mark."""
    elapsed = time.monotonic() - fs.system.timer
    br = max(0.0, min(1.0, fs.brightness))

    # Flash on/off at ~2Hz
    flash = (math.sin(elapsed * 4.0 * math.pi) > -0.3)
    if not flash:
        return

    # Triangle: vertices at (8, 2), (2, 13), (14, 13)
    # Use barycentric test for filled triangle
    ax, ay = 8.0, 2.0
    bx, by = 2.0, 13.0
    cx, cy = 14.0, 13.0

    for y in range(GRID_SIZE):
        for x in range(GRID_SIZE):
            px = x + 0.5
            py = y + 0.5
            # Barycentric coordinates
            denom = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
            if abs(denom) < 0.001:
                continue
            u = ((by - cy) * (px - cx) + (cx - bx) * (py - cy)) / denom
            v = ((cy - ay) * (px - cx) + (ax - cx) * (py - cy)) / denom
            w = 1.0 - u - v
            if u >= 0 and v >= 0 and w >= 0:
                # Inside triangle - amber/yellow fill
                r, g, b = 255, 180, 0
                # Exclamation mark: column 7-8, rows 5-9 (stem) and row 11 (dot)
                if 7.0 <= px <= 9.0:
                    if 5.0 <= py <= 9.0 or 10.5 <= py <= 12.0:
                        r, g, b = 40, 10, 0  # dark on amber
                grid[y][x] = (int(r * br), int(g * br), int(b * br))


def _render_system_low_battery(grid: list[list[tuple[int, int, int]]],
                               fs: FaceState) -> None:
    """Low battery: battery outline with fill level + blinking red ! when critical."""
    elapsed = time.monotonic() - fs.system.timer
    br = max(0.0, min(1.0, fs.brightness))
    level = max(0.0, min(1.0, fs.system.param))  # 0..1 battery level

    # Battery body: columns 3..12, rows 4..11
    # Battery tip: columns 12..13, rows 6..9
    body_l, body_r = 3, 12
    body_t, body_b = 4, 11
    tip_l, tip_r = 12, 14
    tip_t, tip_b = 6, 9

    # Color based on level
    if level > 0.4:
        fill_color = (40, 200, 40)    # green
    elif level > 0.15:
        fill_color = (255, 180, 0)    # amber
    else:
        fill_color = (180, 0, 0)      # dim red background

    outline_color = (120, 120, 130)

    # Fill width based on level (inside the body: cols 4..11 = 8 cols)
    fill_right = body_l + 1 + max(1, int(level * 8))

    # Blinking ! when critical (< 15%)
    critical = level <= 0.15
    # Blink at ~2Hz: on for 60% of cycle, off for 40%
    bang_visible = critical and ((elapsed * 2.0) % 1.0 < 0.6)
    # ! geometry inside battery: stem cols 7-8 rows 5-8, dot cols 7-8 row 10
    bang_color = (255, 40, 20)

    for y in range(GRID_SIZE):
        for x in range(GRID_SIZE):
            # Battery tip (positive terminal nub)
            if tip_t <= y <= tip_b and tip_l <= x <= tip_r:
                grid[y][x] = (int(outline_color[0] * br),
                              int(outline_color[1] * br),
                              int(outline_color[2] * br))
                continue

            # Body outline + interior
            if body_l <= x <= body_r and body_t <= y <= body_b:
                is_outline = (x == body_l or x == body_r or
                              y == body_t or y == body_b)
                if is_outline:
                    grid[y][x] = (int(outline_color[0] * br),
                                  int(outline_color[1] * br),
                                  int(outline_color[2] * br))
                elif body_l < x < body_r and body_t < y < body_b:
                    # Blinking ! takes priority inside the battery
                    if bang_visible and x in (7, 8):
                        if 5 <= y <= 8 or y == 10:
                            grid[y][x] = (int(bang_color[0] * br),
                                          int(bang_color[1] * br),
                                          int(bang_color[2] * br))
                            continue
                    # Fill bar
                    if x < fill_right:
                        grid[y][x] = (int(fill_color[0] * br),
                                      int(fill_color[1] * br),
                                      int(fill_color[2] * br))


def _render_system_updating(grid: list[list[tuple[int, int, int]]],
                            fs: FaceState) -> None:
    """Updating/loading: spinning arc around center."""
    elapsed = time.monotonic() - fs.system.timer
    br = max(0.0, min(1.0, fs.brightness))

    # Spinning arc: radius 5, arc length ~120 degrees, rotates at 2 rev/s
    radius = 5.0
    thickness = 1.6
    arc_len = math.pi * 0.7  # ~126 degrees
    angle_offset = elapsed * 4.0 * math.pi  # 2 rev/s

    for y in range(GRID_SIZE):
        for x in range(GRID_SIZE):
            dx = (x + 0.5) - _CENTER
            dy = (y + 0.5) - _CENTER
            dist = math.sqrt(dx * dx + dy * dy)
            if abs(dist - radius) > thickness:
                continue
            # Angle of this pixel
            angle = math.atan2(dy, dx) - angle_offset
            # Normalize to 0..2pi
            angle = angle % (2.0 * math.pi)
            if angle < arc_len:
                # Fade along arc (brightest at leading edge)
                t = angle / arc_len
                intensity = 1.0 - t * 0.6
                r = int(60 * intensity * br)
                g = int(160 * intensity * br)
                b = int(255 * intensity * br)
                grid[y][x] = (r, g, b)

    # Small dots at center to indicate progress
    dot_count = int(elapsed * 1.5) % 4  # 0..3 cycling dots
    for i in range(dot_count):
        dx = i - 1  # positions: -1, 0, 1, 2 centered
        px = int(_CENTER) + dx
        py = int(_CENTER)
        if 0 <= px < GRID_SIZE:
            grid[py][px] = (int(100 * br), int(180 * br), int(255 * br))


def _render_system_shutdown(grid: list[list[tuple[int, int, int]]],
                            fs: FaceState) -> None:
    """Shutdown: bright dot shrinks to center and fades out."""
    elapsed = time.monotonic() - fs.system.timer
    br = max(0.0, min(1.0, fs.brightness))

    if elapsed > 2.0:
        return  # stay dark

    # Shrinking filled circle from radius 8 down to 0 over 1.5s
    # then brief dot flash at 1.5..2.0
    if elapsed < 1.5:
        t = elapsed / 1.5
        radius = 8.0 * (1.0 - t * t)  # quadratic ease-in
        alpha = 1.0
    else:
        # Brief final dot blink
        t = (elapsed - 1.5) / 0.5
        radius = 0.8
        alpha = 1.0 - t

    color = (30, 120, 255)

    for y in range(GRID_SIZE):
        for x in range(GRID_SIZE):
            dx = (x + 0.5) - _CENTER
            dy = (y + 0.5) - _CENTER
            dist = math.sqrt(dx * dx + dy * dy)
            if dist <= radius:
                # Soft edge
                edge = max(0.0, 1.0 - max(0.0, dist - radius + 1.0))
                r = int(color[0] * alpha * edge * br)
                g = int(color[1] * alpha * edge * br)
                b = int(color[2] * alpha * edge * br)
                grid[y][x] = (r, g, b)


def _render_system_mode(grid: list[list[tuple[int, int, int]]],
                        fs: FaceState) -> bool:
    """Render system mode onto grid.  Returns True if system mode is active."""
    mode = fs.system.mode
    if mode == SystemMode.NONE:
        return False
    elif mode == SystemMode.BOOTING:
        _render_system_booting(grid, fs)
    elif mode == SystemMode.ERROR:
        _render_system_error(grid, fs)
    elif mode == SystemMode.LOW_BATTERY:
        _render_system_low_battery(grid, fs)
    elif mode == SystemMode.UPDATING:
        _render_system_updating(grid, fs)
    elif mode == SystemMode.SHUTTING_DOWN:
        _render_system_shutdown(grid, fs)
    return True


# ── Mouth renderer ───────────────────────────────────────────────────

MOUTH_CX = 8.0           # horizontal center of mouth
MOUTH_CY = 12.5          # vertical center (moved up with more room below eyes)
MOUTH_HALF_W = 4.0       # half-width of mouth in pixels (wider)
MOUTH_THICKNESS = 1.0    # line thickness


def _render_mouth(grid: list[list[tuple[int, int, int]]],
                  fs: FaceState) -> None:
    """Draw a curved mouth line at the bottom of the grid.

    mouth_curve:    -1..+1 (frown to smile), controls parabolic bend.
    mouth_open:     0..1, adds a filled area below the curve line.
    mouth_wave:     0..1, adds sine wobble to curve (snarl / bared teeth).
    mouth_offset_x: -2..+2, shifts mouth center horizontally (smirk).
    mouth_width:    0.3..1.5, scales mouth width (pucker to wide).
    """
    if not fs.mouth:
        return

    curve = fs.mouth_curve         # -1 frown .. +1 smile
    openness = fs.mouth_open       # 0 closed .. 1 open
    wave = fs.mouth_wave           # 0 none .. 1 full wobble
    offset_x = fs.mouth_offset_x  # horizontal shift in pixels
    width_scale = fs.mouth_width   # width multiplier
    br = max(0.0, min(1.0, fs.brightness))
    color = get_emotion_color(fs)

    # Apply offset and width scaling
    cx = MOUTH_CX + offset_x
    half_w = MOUTH_HALF_W * width_scale

    # Bend amount in pixels (positive = smile curves down = lower at edges)
    bend = -curve * 2.5  # flip: positive curve → upward smile

    for y in range(GRID_SIZE):
        for x in range(GRID_SIZE):
            px = x + 0.5
            py = y + 0.5

            # Horizontal distance from mouth center, normalized to -1..1
            dx = px - cx
            if abs(dx) > half_w + 0.5:
                continue

            t = dx / max(half_w, 0.1)  # -1 at left edge, +1 at right edge

            # Parabolic curve: y offset at this x position
            curve_y = MOUTH_CY + bend * t * t

            # Wave wobble: sine displacement along the curve (bared teeth)
            if wave > 0.01:
                curve_y += wave * 1.2 * math.sin(t * math.pi * 4.0)

            # Distance from pixel to the curve line
            dist_to_curve = py - curve_y

            # Mouth line (always drawn)
            if abs(dx) <= half_w and abs(dist_to_curve) < MOUTH_THICKNESS:
                # Fade at the horizontal edges
                edge_fade = 1.0 - max(0.0, (abs(dx) - half_w + 1.0))
                edge_fade = max(0.0, min(1.0, edge_fade))
                r = int(color[0] * br * edge_fade)
                g = int(color[1] * br * edge_fade)
                b = int(color[2] * br * edge_fade)
                grid[y][x] = (r, g, b)

            # Open mouth fill (below the curve line)
            elif openness > 0.05 and abs(dx) <= half_w:
                fill_depth = openness * 3.0  # max 3px deep (more room)
                if 0 < dist_to_curve < fill_depth:
                    # Darker interior
                    fade = 1.0 - dist_to_curve / fill_depth
                    r = int(color[0] * 0.3 * br * fade)
                    g = int(color[1] * 0.3 * br * fade)
                    b = int(color[2] * 0.3 * br * fade)
                    grid[y][x] = (r, g, b)


# ── Main render function ─────────────────────────────────────────────

def render_face(fs: FaceState) -> list[list[tuple[int, int, int]]]:
    """Render both eyes onto a single 16x16 grid.  Returns grid[y][x]."""
    grid: list[list[tuple[int, int, int]]] = [
        [BG_COLOR] * GRID_SIZE for _ in range(GRID_SIZE)
    ]

    # System mode takes over the entire grid
    if _render_system_mode(grid, fs):
        return grid

    _render_eye_onto(grid, fs, is_left=True)
    _render_eye_onto(grid, fs, is_left=False)
    _render_mouth(grid, fs)

    # Post-processing effects
    _apply_afterglow(grid, fs)
    _apply_sparkle(grid, fs)
    _apply_fire(grid, fs)

    # Store current frame for next frame's afterglow
    if fs.fx.afterglow:
        fs.fx.afterglow_grid = [row[:] for row in grid]

    return grid
