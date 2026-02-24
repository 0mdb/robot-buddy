/**
 * Conversation border renderer — visual state + SDF border frame + corner buttons.
 *
 * Ported from tools/face_sim_v3/render/border.py.
 * Reads ConvState from protocol bridge; manages visual interpolation
 * (alpha, color, orbit) separately from the supervisor's state machine.
 */

import {
  ATTENTION_DEPTH,
  BORDER_BLEND_RATE,
  BORDER_CORNER_R,
  BORDER_FRAME_W,
  BORDER_GLOW_W,
  BTN_CORNER_INNER_R,
  BTN_ICON_SIZE,
  BTN_LEFT_ICON_CX,
  BTN_LEFT_ICON_CY,
  BTN_LEFT_ZONE_X1,
  BTN_RIGHT_ICON_CX,
  BTN_RIGHT_ICON_CY,
  BTN_RIGHT_ZONE_X0,
  BTN_ZONE_Y_TOP,
  ButtonIcon,
  ButtonState,
  CONV_COLORS,
  ConvState,
  DONE_FADE_SPEED,
  ERROR_DECAY_RATE,
  ERROR_FLASH_DURATION,
  LED_SCALE,
  LISTENING_ALPHA_BASE,
  LISTENING_ALPHA_MOD,
  LISTENING_BREATH_FREQ,
  PTT_ALPHA_BASE,
  PTT_ALPHA_MOD,
  PTT_PULSE_FREQ,
  type RGB,
  SCREEN_H,
  SCREEN_W,
  SPEAKING_ALPHA_BASE,
  SPEAKING_ALPHA_MOD,
  THINKING_BORDER_ALPHA,
  THINKING_ORBIT_DOT_R,
  THINKING_ORBIT_DOTS,
  THINKING_ORBIT_SPACING,
  THINKING_ORBIT_SPEED,
} from './constants'
import { sdCross, sdfAlpha, sdRoundedBox, setPxBlend } from './sdf'

// ── Border state ────────────────────────────────────────────────

export interface BorderState {
  alpha: number
  color: RGB
  orbit_pos: number
  led_color: RGB
  energy: number

  btn_left_icon: number
  btn_left_state: number
  btn_left_color: RGB
  btn_right_icon: number
  btn_right_state: number
  btn_right_color: RGB
  _btn_left_flash: number
  _btn_right_flash: number

  _conv_state: number
  _conv_timer: number
}

export function createBorderState(): BorderState {
  return {
    alpha: 0.0,
    color: [0, 0, 0],
    orbit_pos: 0.0,
    led_color: [0, 0, 0],
    energy: 0.0,

    btn_left_icon: ButtonIcon.MIC,
    btn_left_state: ButtonState.IDLE,
    btn_left_color: [0, 0, 0],
    btn_right_icon: ButtonIcon.X_MARK,
    btn_right_state: ButtonState.IDLE,
    btn_right_color: [0, 0, 0],
    _btn_left_flash: 0.0,
    _btn_right_flash: 0.0,

    _conv_state: ConvState.IDLE,
    _conv_timer: 0.0,
  }
}

// ── Helpers ─────────────────────────────────────────────────────

const BTN_IDLE_BG: RGB = [40, 44, 52]
const BTN_IDLE_BORDER: RGB = [80, 90, 100]
const BTN_IDLE_ALPHA = 0.35
const BTN_ICON_COLOR: RGB = [200, 210, 220]

function clamp(x: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, x))
}

function lerpColor(c1: RGB, c2: RGB, t: number): RGB {
  const tc = clamp(t, 0.0, 1.0)
  return [
    ((c1[0] + (c2[0] - c1[0]) * tc) | 0) as number,
    ((c1[1] + (c2[1] - c1[1]) * tc) | 0) as number,
    ((c1[2] + (c2[2] - c1[2]) * tc) | 0) as number,
  ]
}

function scaleColor(c: RGB, s: number): RGB {
  return [
    Math.max(0, Math.min(255, (c[0] * s) | 0)),
    Math.max(0, Math.min(255, (c[1] * s) | 0)),
    Math.max(0, Math.min(255, (c[2] * s) | 0)),
  ]
}

// ── Inner SDF ───────────────────────────────────────────────────

const INNER_HW = SCREEN_W / 2.0 - BORDER_FRAME_W
const INNER_HH = SCREEN_H / 2.0 - BORDER_FRAME_W
const CX = SCREEN_W / 2.0
const CY = SCREEN_H / 2.0

function innerSdf(px: number, py: number): number {
  const r = BORDER_CORNER_R
  const dx = Math.abs(px - CX) - INNER_HW + r
  const dy = Math.abs(py - CY) - INNER_HH + r
  return (
    Math.min(Math.max(dx, dy), 0.0) + Math.sqrt(Math.max(dx, 0) ** 2 + Math.max(dy, 0) ** 2) - r
  )
}

function perimeterXY(t: number): [number, number] {
  const inset = BORDER_FRAME_W / 2.0
  const w = SCREEN_W - 2 * inset
  const h = SCREEN_H - 2 * inset
  const perim = 2.0 * (w + h)
  let d = (((t % 1.0) + 1.0) % 1.0) * perim
  if (d < w) return [inset + d, inset]
  d -= w
  if (d < h) return [inset + w, inset + d]
  d -= h
  if (d < w) return [inset + w - d, inset + h]
  d -= w
  return [inset, inset + h - d]
}

// ── State updates ───────────────────────────────────────────────

export function borderSetEnergy(bs: BorderState, energy: number): void {
  bs.energy = clamp(energy, 0.0, 1.0)
}

export function borderSetButtonLeft(
  bs: BorderState,
  icon: number,
  state: number,
  color?: RGB,
): void {
  bs.btn_left_icon = icon
  bs.btn_left_state = state
  if (color !== undefined) bs.btn_left_color = color
  if (state === ButtonState.PRESSED) bs._btn_left_flash = 0.15
}

export function borderSetButtonRight(
  bs: BorderState,
  icon: number,
  state: number,
  color?: RGB,
): void {
  bs.btn_right_icon = icon
  bs.btn_right_state = state
  if (color !== undefined) bs.btn_right_color = color
  if (state === ButtonState.PRESSED) bs._btn_right_flash = 0.15
}

export function borderUpdate(bs: BorderState, state: ConvState, timer: number, dt: number): void {
  bs._conv_state = state
  bs._conv_timer = timer

  if (state === ConvState.IDLE) {
    bs.alpha = clamp(bs.alpha - dt * BORDER_BLEND_RATE, 0.0, 1.0)
  } else if (state === ConvState.ATTENTION) {
    if (timer < 0.4) {
      bs.alpha = 1.0
      bs.color = [...CONV_COLORS[ConvState.ATTENTION]] as RGB
    }
  } else if (state === ConvState.LISTENING) {
    const target =
      LISTENING_ALPHA_BASE +
      LISTENING_ALPHA_MOD * Math.sin(timer * 2.0 * Math.PI * LISTENING_BREATH_FREQ)
    bs.alpha += (target - bs.alpha) * Math.min(1.0, dt * BORDER_BLEND_RATE)
    bs.color = lerpColor(
      bs.color,
      CONV_COLORS[ConvState.LISTENING],
      Math.min(1.0, dt * BORDER_BLEND_RATE),
    )
  } else if (state === ConvState.PTT) {
    const target = PTT_ALPHA_BASE + PTT_ALPHA_MOD * Math.sin(timer * 2.0 * Math.PI * PTT_PULSE_FREQ)
    bs.alpha += (target - bs.alpha) * Math.min(1.0, dt * BORDER_BLEND_RATE)
    bs.color = lerpColor(
      bs.color,
      CONV_COLORS[ConvState.PTT],
      Math.min(1.0, dt * BORDER_BLEND_RATE),
    )
  } else if (state === ConvState.THINKING) {
    const target = THINKING_BORDER_ALPHA
    bs.alpha += (target - bs.alpha) * Math.min(1.0, dt * BORDER_BLEND_RATE)
    bs.color = lerpColor(
      bs.color,
      CONV_COLORS[ConvState.THINKING],
      Math.min(1.0, dt * BORDER_BLEND_RATE),
    )
    bs.orbit_pos = (bs.orbit_pos + THINKING_ORBIT_SPEED * dt) % 1.0
  } else if (state === ConvState.SPEAKING) {
    const target = SPEAKING_ALPHA_BASE + SPEAKING_ALPHA_MOD * bs.energy
    bs.alpha += (target - bs.alpha) * Math.min(1.0, dt * BORDER_BLEND_RATE)
    bs.color = lerpColor(
      bs.color,
      CONV_COLORS[ConvState.SPEAKING],
      Math.min(1.0, dt * BORDER_BLEND_RATE),
    )
  } else if (state === ConvState.ERROR) {
    if (timer < ERROR_FLASH_DURATION) {
      bs.alpha = 1.0
      bs.color = [...CONV_COLORS[ConvState.ERROR]] as RGB
    } else {
      bs.alpha = Math.exp(-(timer - ERROR_FLASH_DURATION) * ERROR_DECAY_RATE)
    }
  } else if (state === ConvState.DONE) {
    bs.alpha = clamp(bs.alpha - dt * DONE_FADE_SPEED, 0.0, 1.0)
  }

  // LED mirrors border color at reduced brightness
  if (bs.alpha > 0.01) {
    bs.led_color = scaleColor(bs.color, bs.alpha * LED_SCALE)
  } else {
    bs.led_color = [0, 0, 0]
  }

  // Button flash decay
  if (bs._btn_left_flash > 0) {
    bs._btn_left_flash = Math.max(0.0, bs._btn_left_flash - dt)
    if (bs._btn_left_flash <= 0 && bs.btn_left_state === ButtonState.PRESSED) {
      bs.btn_left_state = ButtonState.ACTIVE
    }
  }
  if (bs._btn_right_flash > 0) {
    bs._btn_right_flash = Math.max(0.0, bs._btn_right_flash - dt)
    if (bs._btn_right_flash <= 0 && bs.btn_right_state === ButtonState.PRESSED) {
      bs.btn_right_state = ButtonState.ACTIVE
    }
  }
}

// ── Frame rendering ─────────────────────────────────────────────

export function borderRender(bs: BorderState, buf: Uint8ClampedArray): void {
  if (bs.alpha < 0.01 && bs._conv_state !== ConvState.ATTENTION) return

  if (bs._conv_state === ConvState.ATTENTION && bs._conv_timer < 0.4) {
    renderAttention(bs, buf)
    return
  }

  const depth = BORDER_FRAME_W + BORDER_GLOW_W
  for (let y = 0; y < SCREEN_H; y++) {
    const dv = Math.min(y, SCREEN_H - 1 - y)
    const row = y * SCREEN_W
    if (dv >= depth) {
      for (let x = 0; x < depth; x++) framePx(bs, buf, row + x, x, y)
      for (let x = SCREEN_W - depth; x < SCREEN_W; x++) framePx(bs, buf, row + x, x, y)
    } else {
      for (let x = 0; x < SCREEN_W; x++) {
        const dh = Math.min(x, SCREEN_W - 1 - x)
        if (dh >= depth && dv >= depth) continue
        framePx(bs, buf, row + x, x, y)
      }
    }
  }

  if (bs._conv_state === ConvState.THINKING && bs.alpha > 0.01) {
    renderDots(bs, buf)
  }
}

function framePx(bs: BorderState, buf: Uint8ClampedArray, idx: number, x: number, y: number): void {
  const d = innerSdf(x + 0.5, y + 0.5)
  let a: number
  if (d > 0) {
    a = bs.alpha
  } else if (d > -BORDER_GLOW_W) {
    const t = (d + BORDER_GLOW_W) / BORDER_GLOW_W
    a = bs.alpha * t * t
  } else {
    return
  }
  if (a > 0.01) {
    setPxBlend(buf, idx, bs.color[0], bs.color[1], bs.color[2], a)
  }
}

function renderAttention(bs: BorderState, buf: Uint8ClampedArray): void {
  const progress = bs._conv_timer / 0.4
  const sweep = ATTENTION_DEPTH * progress
  const col = CONV_COLORS[ConvState.ATTENTION]
  const fadeGlobal = 1.0 - progress * 0.5
  const limit = (sweep | 0) + 1

  for (let y = 0; y < SCREEN_H; y++) {
    const dv = Math.min(y, SCREEN_H - 1 - y)
    const row = y * SCREEN_W
    if (dv > limit) {
      for (let x = 0; x < Math.min(limit, SCREEN_W); x++) {
        attnPx(buf, row + x, x, sweep, col, fadeGlobal)
      }
      for (let x = Math.max(0, SCREEN_W - limit); x < SCREEN_W; x++) {
        attnPx(buf, row + x, Math.min(x, SCREEN_W - 1 - x), sweep, col, fadeGlobal)
      }
    } else {
      for (let x = 0; x < SCREEN_W; x++) {
        const d = Math.min(x, dv, SCREEN_W - 1 - x)
        attnPx(buf, row + x, d, sweep, col, fadeGlobal)
      }
    }
  }
}

function attnPx(
  buf: Uint8ClampedArray,
  idx: number,
  dist: number,
  sweep: number,
  col: RGB,
  fade: number,
): void {
  if (dist >= sweep) return
  const f = (1.0 - dist / Math.max(1.0, sweep)) * fade
  const a = f * f
  if (a > 0.01) {
    setPxBlend(buf, idx, col[0], col[1], col[2], a)
  }
}

function renderDots(bs: BorderState, buf: Uint8ClampedArray): void {
  const brightnesses = [1.0, 0.7, 0.4]
  const dotCol = CONV_COLORS[ConvState.THINKING]
  for (let i = 0; i < THINKING_ORBIT_DOTS; i++) {
    const pos = (((bs.orbit_pos - i * THINKING_ORBIT_SPACING) % 1.0) + 1.0) % 1.0
    const [dx, dy] = perimeterXY(pos)
    const bri = i < brightnesses.length ? brightnesses[i] : 0.3
    const c = scaleColor(dotCol, bri)
    const r = THINKING_ORBIT_DOT_R
    const x0 = Math.max(0, (dx - r - 1) | 0)
    const x1 = Math.min(SCREEN_W, (dx + r + 2) | 0)
    const y0 = Math.max(0, (dy - r - 1) | 0)
    const y1 = Math.min(SCREEN_H, (dy + r + 2) | 0)
    for (let y = y0; y < y1; y++) {
      const row = y * SCREEN_W
      for (let x = x0; x < x1; x++) {
        const d = Math.sqrt((x + 0.5 - dx) ** 2 + (y + 0.5 - dy) ** 2)
        if (d < r) {
          const a = Math.min(1.0, (1.0 - (d / r) ** 2) * 2.5)
          if (a > 0.01) {
            setPxBlend(buf, row + x, c[0], c[1], c[2], a)
          }
        }
      }
    }
  }
}

// ── Corner button rendering ─────────────────────────────────────

export function borderRenderButtons(bs: BorderState, buf: Uint8ClampedArray): void {
  if (bs.btn_left_icon !== ButtonIcon.NONE) {
    drawButtonZone(bs, buf, true)
  }
  if (bs.btn_right_icon !== ButtonIcon.NONE) {
    drawButtonZone(bs, buf, false)
  }
}

function drawButtonZone(bs: BorderState, buf: Uint8ClampedArray, isLeft: boolean): void {
  const icon = isLeft ? bs.btn_left_icon : bs.btn_right_icon
  const state = isLeft ? bs.btn_left_state : bs.btn_right_state
  const activeColor = isLeft ? bs.btn_left_color : bs.btn_right_color
  const flash = isLeft ? bs._btn_left_flash : bs._btn_right_flash

  let bgCol: RGB
  let bgAlpha: number
  let borderCol: RGB
  let iconCol: RGB

  if (state === ButtonState.PRESSED || flash > 0) {
    bgCol = scaleColor(activeColor, 1.3)
    bgAlpha = 0.75
    borderCol = [255, 255, 255]
    iconCol = [255, 255, 255]
  } else if (state === ButtonState.ACTIVE) {
    bgCol = activeColor
    bgAlpha = 0.55
    borderCol = scaleColor(activeColor, 1.2)
    iconCol = [255, 255, 255]
  } else {
    bgCol = BTN_IDLE_BG
    bgAlpha = BTN_IDLE_ALPHA
    borderCol = BTN_IDLE_BORDER
    iconCol = BTN_ICON_COLOR
  }

  drawCornerZone(buf, isLeft, bgCol, bgAlpha, borderCol)

  const icx = isLeft ? BTN_LEFT_ICON_CX : BTN_RIGHT_ICON_CX
  const icy = isLeft ? BTN_LEFT_ICON_CY : BTN_RIGHT_ICON_CY
  const active = state !== ButtonState.IDLE
  drawIcon(buf, icx, icy, icon, iconCol, BTN_ICON_SIZE, bs._conv_timer, active)
}

function drawCornerZone(
  buf: Uint8ClampedArray,
  isLeft: boolean,
  bgCol: RGB,
  bgAlpha: number,
  borderCol: RGB,
): void {
  const R = BTN_CORNER_INNER_R
  const x0 = isLeft ? 0 : BTN_RIGHT_ZONE_X0
  const x1 = isLeft ? BTN_LEFT_ZONE_X1 : SCREEN_W
  const rcx = isLeft ? BTN_LEFT_ZONE_X1 - R : BTN_RIGHT_ZONE_X0 + R
  const rcy = BTN_ZONE_Y_TOP + R

  for (let y = BTN_ZONE_Y_TOP; y < SCREEN_H; y++) {
    const row = y * SCREEN_W
    for (let x = x0; x < x1; x++) {
      const px = x + 0.5
      const py = y + 0.5

      const inCornerQuad = isLeft ? px > rcx && py < rcy : px < rcx && py < rcy

      if (inCornerQuad) {
        const dx = px - rcx
        const dy = py - rcy
        const dist = Math.sqrt(dx * dx + dy * dy)
        if (dist > R + 0.5) continue
        if (dist > R - 0.5) {
          const a = bgAlpha * clamp(R + 0.5 - dist, 0.0, 1.0)
          if (a > 0.01) setPxBlend(buf, row + x, bgCol[0], bgCol[1], bgCol[2], a)
          const ba = clamp(1.0 - Math.abs(dist - R), 0.0, 1.0) * 0.6
          if (ba > 0.01) setPxBlend(buf, row + x, borderCol[0], borderCol[1], borderCol[2], ba)
          continue
        }
      }

      setPxBlend(buf, row + x, bgCol[0], bgCol[1], bgCol[2], bgAlpha)

      const onTop = y === BTN_ZONE_Y_TOP && !inCornerQuad
      const onInnerSide = isLeft ? x === x1 - 1 : x === x0
      if (onInnerSide && py >= rcy) {
        setPxBlend(buf, row + x, borderCol[0], borderCol[1], borderCol[2], 0.6)
      } else if (onTop) {
        const onTopValid = isLeft ? px <= rcx : px >= rcx
        if (onTopValid) {
          setPxBlend(buf, row + x, borderCol[0], borderCol[1], borderCol[2], 0.6)
        }
      }
    }
  }
}

// ── Icon dispatch ───────────────────────────────────────────────

function sdLineSeg(px: number, py: number, ax: number, ay: number, bx: number, by: number): number {
  const dx = bx - ax
  const dy = by - ay
  const lenSq = dx * dx + dy * dy
  if (lenSq < 1e-10) return Math.sqrt((px - ax) ** 2 + (py - ay) ** 2)
  const t = clamp(((px - ax) * dx + (py - ay) * dy) / lenSq, 0.0, 1.0)
  const cx = ax + t * dx
  const cy = ay + t * dy
  return Math.sqrt((px - cx) ** 2 + (py - cy) ** 2)
}

function drawIcon(
  buf: Uint8ClampedArray,
  cx: number,
  cy: number,
  icon: number,
  color: RGB,
  size: number,
  timer: number,
  active: boolean,
): void {
  if (icon === ButtonIcon.NONE) return
  if (icon === ButtonIcon.MIC) iconMic(buf, cx, cy, color, size, timer, active)
  else if (icon === ButtonIcon.X_MARK) iconXMark(buf, cx, cy, color, size)
  else if (icon === ButtonIcon.CHECK) iconCheck(buf, cx, cy, color, size)
  else if (icon === ButtonIcon.REPEAT) iconRepeat(buf, cx, cy, color, size)
  else if (icon === ButtonIcon.STAR) iconStar(buf, cx, cy, color, size)
  else if (icon === ButtonIcon.SPEAKER) iconSpeaker(buf, cx, cy, color, size, timer, active)
}

// ── Icon renderers ──────────────────────────────────────────────

function iconMic(
  buf: Uint8ClampedArray,
  cx: number,
  cy: number,
  color: RGB,
  size: number,
  timer: number,
  active: boolean,
): void {
  const micCx = cx - size * 0.22
  const bodyHw = size * 0.19
  const bodyHh = size * 0.39
  const bodyR = bodyHw
  const baseY = cy + size * 0.5
  const baseHw = size * 0.22
  const baseHh = size * 0.06
  const arcRadii = [size * 0.44, size * 0.67, size * 0.89]
  const arcThick = size * 0.072
  const arcMin = (-70.0 * Math.PI) / 180.0
  const arcMax = (70.0 * Math.PI) / 180.0

  const x0 = Math.max(0, (cx - size - 1) | 0)
  const x1 = Math.min(SCREEN_W, (cx + size + 1) | 0)
  const y0 = Math.max(0, (cy - size - 1) | 0)
  const y1 = Math.min(SCREEN_H, (cy + size + 1) | 0)

  for (let y = y0; y < y1; y++) {
    const row = y * SCREEN_W
    for (let x = x0; x < x1; x++) {
      const px = x + 0.5
      const py = y + 0.5

      const dBody = sdRoundedBox(px, py, micCx, cy, bodyHw, bodyHh, bodyR)
      const aBody = sdfAlpha(dBody)
      if (aBody > 0.01) {
        setPxBlend(buf, row + x, color[0], color[1], color[2], aBody * 0.9)
        continue
      }

      const dBase = sdRoundedBox(px, py, micCx, baseY, baseHw, baseHh, 0.5)
      const aBase = sdfAlpha(dBase)
      if (aBase > 0.01) {
        setPxBlend(buf, row + x, color[0], color[1], color[2], aBase * 0.7)
        continue
      }

      const dxA = px - micCx
      const dyA = py - cy
      const dist = Math.sqrt(dxA * dxA + dyA * dyA)
      const angle = Math.atan2(dyA, dxA)
      if (angle >= arcMin && angle <= arcMax) {
        for (const ar of arcRadii) {
          const ad = Math.abs(dist - ar)
          if (ad < arcThick) {
            let a = 1.0 - ad / arcThick
            if (active) {
              const phase = (((timer * 3.0 - ar / (size * 0.78)) % 1.0) + 1.0) % 1.0
              a *= 0.5 + 0.5 * Math.max(0.0, Math.sin(phase * Math.PI))
            }
            setPxBlend(buf, row + x, color[0], color[1], color[2], a * 0.9)
            break
          }
        }
      }
    }
  }
}

function iconXMark(buf: Uint8ClampedArray, cx: number, cy: number, color: RGB, size: number): void {
  const arm = size * 0.5
  const thick = size * 0.14
  const x0 = Math.max(0, (cx - arm - 2) | 0)
  const x1 = Math.min(SCREEN_W, (cx + arm + 2) | 0)
  const y0 = Math.max(0, (cy - arm - 2) | 0)
  const y1 = Math.min(SCREEN_H, (cy + arm + 2) | 0)
  for (let y = y0; y < y1; y++) {
    const row = y * SCREEN_W
    for (let x = x0; x < x1; x++) {
      const d = sdCross(x + 0.5, y + 0.5, cx, cy, arm, thick)
      const a = sdfAlpha(d)
      if (a > 0.01) {
        setPxBlend(buf, row + x, color[0], color[1], color[2], a * 0.9)
      }
    }
  }
}

function iconCheck(buf: Uint8ClampedArray, cx: number, cy: number, color: RGB, size: number): void {
  const thick = size * 0.14
  const vx = cx - size * 0.1
  const vy = cy + size * 0.15
  const a1x = vx - size * 0.25
  const a1y = vy - size * 0.2
  const a2x = vx + size * 0.45
  const a2y = vy - size * 0.45

  const x0 = Math.max(0, (cx - size - 1) | 0)
  const x1 = Math.min(SCREEN_W, (cx + size + 1) | 0)
  const y0 = Math.max(0, (cy - size - 1) | 0)
  const y1 = Math.min(SCREEN_H, (cy + size + 1) | 0)

  for (let y = y0; y < y1; y++) {
    const row = y * SCREEN_W
    for (let x = x0; x < x1; x++) {
      const px = x + 0.5
      const py = y + 0.5
      const d1 = sdLineSeg(px, py, a1x, a1y, vx, vy) - thick
      const d2 = sdLineSeg(px, py, vx, vy, a2x, a2y) - thick
      const d = Math.min(d1, d2)
      const a = sdfAlpha(d)
      if (a > 0.01) {
        setPxBlend(buf, row + x, color[0], color[1], color[2], a * 0.9)
      }
    }
  }
}

function triAlpha(
  px: number,
  py: number,
  a: [number, number],
  b: [number, number],
  c: [number, number],
): number {
  const d1 = (px - b[0]) * (a[1] - b[1]) - (a[0] - b[0]) * (py - b[1])
  const d2 = (px - c[0]) * (b[1] - c[1]) - (b[0] - c[0]) * (py - c[1])
  const d3 = (px - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (py - a[1])
  const hasNeg = d1 < 0 || d2 < 0 || d3 < 0
  const hasPos = d1 > 0 || d2 > 0 || d3 > 0
  if (hasNeg && hasPos) return 0.0
  return 1.0
}

function iconRepeat(
  buf: Uint8ClampedArray,
  cx: number,
  cy: number,
  color: RGB,
  size: number,
): void {
  const ringR = size * 0.45
  const ringThick = size * 0.08
  const gapHalf = (30.0 * Math.PI) / 180.0
  const gapCenter = -Math.PI / 2.0

  const arrowAngle = gapCenter + gapHalf
  const tipX = cx + ringR * Math.cos(arrowAngle)
  const tipY = cy + ringR * Math.sin(arrowAngle)
  const tangAngle = arrowAngle + Math.PI / 2.0
  const arrLen = size * 0.25
  const arrHw = size * 0.15
  const baseX = tipX - arrLen * Math.cos(tangAngle)
  const baseY = tipY - arrLen * Math.sin(tangAngle)
  const perpX = -Math.sin(tangAngle)
  const perpY = Math.cos(tangAngle)
  const triA: [number, number] = [tipX, tipY]
  const triB: [number, number] = [baseX + perpX * arrHw, baseY + perpY * arrHw]
  const triC: [number, number] = [baseX - perpX * arrHw, baseY - perpY * arrHw]

  const x0 = Math.max(0, (cx - size - 1) | 0)
  const x1 = Math.min(SCREEN_W, (cx + size + 1) | 0)
  const y0 = Math.max(0, (cy - size - 1) | 0)
  const y1 = Math.min(SCREEN_H, (cy + size + 1) | 0)

  for (let y = y0; y < y1; y++) {
    const row = y * SCREEN_W
    for (let x = x0; x < x1; x++) {
      const px = x + 0.5
      const py = y + 0.5
      let bestA = 0.0

      const dxR = px - cx
      const dyR = py - cy
      const dist = Math.sqrt(dxR * dxR + dyR * dyR)
      const angle = Math.atan2(dyR, dxR)
      let da = angle - gapCenter
      da = ((((da + Math.PI) % (2.0 * Math.PI)) + 2.0 * Math.PI) % (2.0 * Math.PI)) - Math.PI
      if (Math.abs(da) > gapHalf) {
        const dRing = Math.abs(dist - ringR) - ringThick
        const aRing = sdfAlpha(dRing)
        if (aRing > bestA) bestA = aRing
      }

      const aTri = triAlpha(px, py, triA, triB, triC)
      if (aTri > bestA) bestA = aTri

      if (bestA > 0.01) {
        setPxBlend(buf, row + x, color[0], color[1], color[2], bestA * 0.9)
      }
    }
  }
}

function iconStar(buf: Uint8ClampedArray, cx: number, cy: number, color: RGB, size: number): void {
  const rOuter = size * 0.5
  const rInner = size * 0.22
  const x0 = Math.max(0, (cx - size) | 0)
  const x1 = Math.min(SCREEN_W, (cx + size) | 0)
  const y0 = Math.max(0, (cy - size) | 0)
  const y1 = Math.min(SCREEN_H, (cy + size) | 0)
  const twoPi5 = (2.0 * Math.PI) / 5.0

  for (let y = y0; y < y1; y++) {
    const row = y * SCREEN_W
    for (let x = x0; x < x1; x++) {
      const dxS = x + 0.5 - cx
      const dyS = y + 0.5 - cy
      const dist = Math.sqrt(dxS * dxS + dyS * dyS)
      const angle = Math.atan2(dyS, dxS) + Math.PI / 2.0
      const seg = ((angle % twoPi5) + twoPi5) % twoPi5
      const t = Math.abs(seg / twoPi5 - 0.5) * 2.0
      const edgeR = rInner + (rOuter - rInner) * t
      const d = dist - edgeR
      const a = sdfAlpha(d)
      if (a > 0.01) {
        setPxBlend(buf, row + x, color[0], color[1], color[2], a * 0.9)
      }
    }
  }
}

function iconSpeaker(
  buf: Uint8ClampedArray,
  cx: number,
  cy: number,
  color: RGB,
  size: number,
  timer: number,
  active: boolean,
): void {
  const coneCx = cx - size * 0.2
  const smallHw = size * 0.1
  const smallHh = size * 0.12
  const bigHw = size * 0.1
  const bigHh = size * 0.28
  const bigCx = coneCx - size * 0.15

  const arcCx = coneCx + size * 0.05
  const arcRadii = [size * 0.4, size * 0.6]
  const arcThick = size * 0.072
  const arcMin = (-60.0 * Math.PI) / 180.0
  const arcMax = (60.0 * Math.PI) / 180.0

  const x0 = Math.max(0, (cx - size - 1) | 0)
  const x1 = Math.min(SCREEN_W, (cx + size + 1) | 0)
  const y0 = Math.max(0, (cy - size - 1) | 0)
  const y1 = Math.min(SCREEN_H, (cy + size + 1) | 0)

  for (let y = y0; y < y1; y++) {
    const row = y * SCREEN_W
    for (let x = x0; x < x1; x++) {
      const px = x + 0.5
      const py = y + 0.5

      const d1 = sdRoundedBox(px, py, coneCx, cy, smallHw, smallHh, 1.0)
      const d2 = sdRoundedBox(px, py, bigCx, cy, bigHw, bigHh, 1.0)
      const dCone = Math.min(d1, d2)
      const aCone = sdfAlpha(dCone)
      if (aCone > 0.01) {
        setPxBlend(buf, row + x, color[0], color[1], color[2], aCone * 0.9)
        continue
      }

      const dxA = px - arcCx
      const dyA = py - cy
      const dist = Math.sqrt(dxA * dxA + dyA * dyA)
      const angle = Math.atan2(dyA, dxA)
      if (angle >= arcMin && angle <= arcMax) {
        for (const ar of arcRadii) {
          const ad = Math.abs(dist - ar)
          if (ad < arcThick) {
            let a = 1.0 - ad / arcThick
            if (active) {
              const phase = (((timer * 3.0 - ar / (size * 0.6)) % 1.0) + 1.0) % 1.0
              a *= 0.5 + 0.5 * Math.max(0.0, Math.sin(phase * Math.PI))
            }
            setPxBlend(buf, row + x, color[0], color[1], color[2], a * 0.9)
            break
          }
        }
      }
    }
  }
}
