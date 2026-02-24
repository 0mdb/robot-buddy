/**
 * Face state type definitions + factory functions.
 *
 * Ported from tools/face_sim_v3/state/face_state.py dataclasses.
 */

import { Mood, type RGB, SystemMode } from './constants'

export interface EyeState {
  openness: number
  openness_target: number
  is_open: boolean
  gaze_x: number
  gaze_y: number
  gaze_x_target: number
  gaze_y_target: number
  vx: number
  vy: number
  width_scale: number
  width_scale_target: number
  height_scale: number
  height_scale_target: number
}

export interface EyelidState {
  top_l: number
  top_r: number
  bottom_l: number
  bottom_r: number
  slope: number
  slope_target: number
}

export interface AnimTimers {
  autoblink: boolean
  next_blink: number
  idle: boolean
  next_idle: number
  next_saccade: number

  // Gesture flags + timers (minimal for Phase 1-3; full gestures deferred)
  confused: boolean
  confused_timer: number
  confused_toggle: boolean
  confused_duration: number
  laugh: boolean
  laugh_timer: number
  laugh_toggle: boolean
  laugh_duration: number
  surprise: boolean
  surprise_timer: number
  surprise_duration: number
  heart: boolean
  heart_timer: number
  heart_duration: number
  x_eyes: boolean
  x_eyes_timer: number
  x_eyes_duration: number
  sleepy: boolean
  sleepy_timer: number
  sleepy_duration: number
  rage: boolean
  rage_timer: number
  rage_duration: number
  shy: boolean
  shy_timer: number
  shy_duration: number
  nod: boolean
  nod_timer: number
  nod_duration: number
  headshake: boolean
  headshake_timer: number
  headshake_duration: number

  // Flicker
  h_flicker: boolean
  h_flicker_alt: boolean
  h_flicker_amp: number
  v_flicker: boolean
  v_flicker_alt: boolean
  v_flicker_amp: number

  // Micro-expressions
  micro_expr_next: number
  micro_expr_type: number
  micro_expr_timer: number
  micro_expr_active: boolean
}

export interface EffectsState {
  breathing: boolean
  breath_phase: number
  sparkle: boolean
  sparkle_pixels: Array<[number, number, number]> // [x, y, life]
  edge_glow: boolean
}

export interface SystemState {
  mode: SystemMode
  timer: number
  phase: number
  param: number
}

export interface FaceState {
  eye_l: EyeState
  eye_r: EyeState
  eyelids: EyelidState
  anim: AnimTimers
  fx: EffectsState
  system: SystemState

  mood: Mood
  expression_intensity: number
  brightness: number
  solid_eye: boolean
  show_mouth: boolean
  mood_color_override: RGB | null

  talking: boolean
  talking_energy: number
  talking_phase: number

  // Speech rhythm sync
  _speech_high_frames: number
  _speech_eye_pulse: number
  _speech_low_frames: number
  _speech_pause_fired: boolean

  mouth_curve: number
  mouth_curve_target: number
  mouth_open: number
  mouth_open_target: number
  mouth_wave: number
  mouth_wave_target: number
  mouth_offset_x: number
  mouth_offset_x_target: number
  mouth_width: number
  mouth_width_target: number

  active_gesture: number
  active_gesture_until: number
}

function createEyeState(): EyeState {
  return {
    openness: 1.0,
    openness_target: 1.0,
    is_open: true,
    gaze_x: 0.0,
    gaze_y: 0.0,
    gaze_x_target: 0.0,
    gaze_y_target: 0.0,
    vx: 0.0,
    vy: 0.0,
    width_scale: 1.0,
    width_scale_target: 1.0,
    height_scale: 1.0,
    height_scale_target: 1.0,
  }
}

function createEyelidState(): EyelidState {
  return {
    top_l: 0.0,
    top_r: 0.0,
    bottom_l: 0.0,
    bottom_r: 0.0,
    slope: 0.0,
    slope_target: 0.0,
  }
}

function createAnimTimers(): AnimTimers {
  return {
    autoblink: true,
    next_blink: 0.0,
    idle: true,
    next_idle: 0.0,
    next_saccade: 0.0,
    confused: false,
    confused_timer: 0.0,
    confused_toggle: true,
    confused_duration: 0.5,
    laugh: false,
    laugh_timer: 0.0,
    laugh_toggle: true,
    laugh_duration: 0.5,
    surprise: false,
    surprise_timer: 0.0,
    surprise_duration: 0.8,
    heart: false,
    heart_timer: 0.0,
    heart_duration: 2.0,
    x_eyes: false,
    x_eyes_timer: 0.0,
    x_eyes_duration: 2.5,
    sleepy: false,
    sleepy_timer: 0.0,
    sleepy_duration: 3.0,
    rage: false,
    rage_timer: 0.0,
    rage_duration: 3.0,
    shy: false,
    shy_timer: 0.0,
    shy_duration: 2.0,
    nod: false,
    nod_timer: 0.0,
    nod_duration: 0.35,
    headshake: false,
    headshake_timer: 0.0,
    headshake_duration: 0.35,
    h_flicker: false,
    h_flicker_alt: false,
    h_flicker_amp: 1.5,
    v_flicker: false,
    v_flicker_alt: false,
    v_flicker_amp: 1.5,
    micro_expr_next: 0.0,
    micro_expr_type: 0,
    micro_expr_timer: 0.0,
    micro_expr_active: false,
  }
}

function createEffectsState(): EffectsState {
  return {
    breathing: true,
    breath_phase: 0.0,
    sparkle: true,
    sparkle_pixels: [],
    edge_glow: true,
  }
}

function createSystemState(): SystemState {
  return {
    mode: SystemMode.NONE,
    timer: 0.0,
    phase: 0,
    param: 0.0,
  }
}

export function createFaceState(): FaceState {
  return {
    eye_l: createEyeState(),
    eye_r: createEyeState(),
    eyelids: createEyelidState(),
    anim: createAnimTimers(),
    fx: createEffectsState(),
    system: createSystemState(),

    mood: Mood.NEUTRAL,
    expression_intensity: 1.0,
    brightness: 1.0,
    solid_eye: true,
    show_mouth: true,
    mood_color_override: null,

    talking: false,
    talking_energy: 0.0,
    talking_phase: 0.0,

    _speech_high_frames: 0,
    _speech_eye_pulse: 0.0,
    _speech_low_frames: 0,
    _speech_pause_fired: false,

    mouth_curve: 0.1,
    mouth_curve_target: 0.1,
    mouth_open: 0.0,
    mouth_open_target: 0.0,
    mouth_wave: 0.0,
    mouth_wave_target: 0.0,
    mouth_offset_x: 0.0,
    mouth_offset_x_target: 0.0,
    mouth_width: 1.0,
    mouth_width_target: 1.0,

    active_gesture: 0xff,
    active_gesture_until: 0.0,
  }
}
