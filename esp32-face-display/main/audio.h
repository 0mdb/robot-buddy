#pragma once
// Audio scaffold — ES8311 codec + I2S initialization.
// Playback and mic capture are stubs for future implementation.

#include <cstdint>
#include <cstddef>

// Initialize ES8311 codec via I2C and I2S peripheral.
// Keeps amplifier disabled. Does not start playback.
void audio_init(void);

// Play PCM audio (16-bit, mono, 16kHz). Stub — logs and returns.
void audio_play_pcm(const int16_t* samples, size_t num_samples);

// Stop playback. Stub.
void audio_stop(void);

// Start mic capture. Stub.
void audio_mic_start(void);

// Stop mic capture. Stub.
void audio_mic_stop(void);

// Returns true if audio is currently playing. Always false for now.
bool audio_is_playing(void);
