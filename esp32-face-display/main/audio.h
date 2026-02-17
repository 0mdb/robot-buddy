#pragma once
// Audio driver bring-up for ES8311 codec + I2S.
// Provides simple diagnostics: 1kHz tone and microphone level probe.

#include <cstdint>
#include <cstddef>

// Initialize ES8311 codec via shared I2C bus and I2S peripheral.
void audio_init(void);

// Play PCM audio (16-bit, mono, 16kHz). Writes directly to I2S TX.
void audio_play_pcm(const int16_t* samples, size_t num_samples);

// Stop active playback/diagnostic activity.
void audio_stop(void);

// Start/stop continuous mic mode (reserved for future streaming path).
void audio_mic_start(void);
void audio_mic_stop(void);

// Queue a 1kHz diagnostic tone.
void audio_play_test_tone(uint32_t duration_ms);

// Queue a microphone probe and print RMS/peak stats to log.
void audio_run_mic_probe(uint32_t duration_ms);

// Returns true while DAC path is actively sending samples.
bool audio_is_playing(void);

// Returns true when codec + I2S initialization succeeded.
bool audio_is_ready(void);

// True if last mic probe detected meaningful input level.
bool audio_mic_activity_detected(void);

// Dump all ES8311 registers to serial log (for comparing against known-good).
void audio_dump_codec_regs(void);

// Synchronous boot tone — blocks caller for duration_ms. Use only from
// app_main before worker task or other subsystems start, to test DAC path
// without any task scheduling dependencies.
void audio_boot_tone_sync(uint32_t duration_ms);
