#pragma once
// Face renderer: converts FaceState into a 16x16 RGB pixel buffer.
// Ported from face_render.py.

#include "face_state.h"
#include "config.h"
#include <cstdint>

// Pixel buffer: grid[y][x][channel], where channel 0=R, 1=G, 2=B.
using PixelGrid = uint8_t[GRID_H][GRID_W][3];

// Render the current face state into the pixel grid.
// Clears the grid, draws eyes/mouth or system mode, applies post-processing.
void face_render(const FaceState& fs, PixelGrid grid);
