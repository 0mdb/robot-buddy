"""Visual timeline — scrolling strip of state transition events.

Shows a 15-second window with color-coded markers for:
- Mood changes (colored blocks from MOOD_COLORS)
- Conv state transitions (colored ticks from CONV_COLORS)
- Gesture triggers (white markers)
- Guardrail firings (red markers)
"""

from __future__ import annotations

import time

import pygame

from tools.face_sim_v3.state.constants import (
    CONV_COLORS,
    MOOD_COLORS,
    ConvState,
    GestureId,
    Mood,
)


class TimelineEvent:
    __slots__ = ("timestamp", "kind", "label", "color")

    def __init__(
        self,
        timestamp: float,
        kind: str,
        label: str,
        color: tuple[int, int, int],
    ) -> None:
        self.timestamp = timestamp
        self.kind = kind
        self.label = label
        self.color = color


class Timeline:
    """Scrolling event timeline rendered as a horizontal strip."""

    WINDOW_SEC = 15.0  # Visible time window
    STRIP_H = 30  # Pixel height of the timeline strip

    def __init__(self) -> None:
        self.events: list[TimelineEvent] = []
        self.font: pygame.font.Font | None = None
        self._last_mood: Mood | None = None
        self._last_conv: ConvState | None = None

    def init_font(self) -> None:
        self.font = pygame.font.SysFont("monospace", 11)

    def log_mood(self, mood: Mood) -> None:
        if mood == self._last_mood:
            return
        self._last_mood = mood
        color = MOOD_COLORS.get(mood, (150, 150, 150))
        self.events.append(TimelineEvent(time.monotonic(), "mood", mood.name, color))

    def log_conv(self, state: ConvState) -> None:
        if state == self._last_conv:
            return
        self._last_conv = state
        color = CONV_COLORS.get(state, (100, 100, 100))
        # Use white for IDLE/DONE since their color is black
        if color == (0, 0, 0):
            color = (80, 80, 90)
        self.events.append(TimelineEvent(time.monotonic(), "conv", state.name, color))

    def log_gesture(self, gesture_id: int) -> None:
        try:
            name = GestureId(gesture_id).name
        except ValueError:
            name = f"G{gesture_id}"
        self.events.append(
            TimelineEvent(time.monotonic(), "gesture", name, (255, 255, 255))
        )

    def log_guardrail(self, label: str = "GUARDRAIL") -> None:
        self.events.append(
            TimelineEvent(time.monotonic(), "guardrail", label, (255, 50, 50))
        )

    def render(self, surface: pygame.Surface, x: int, y: int, width: int) -> None:
        if self.font is None:
            self.init_font()
        font = self.font
        assert font is not None

        now = time.monotonic()
        t_start = now - self.WINDOW_SEC

        # Prune old events
        self.events = [e for e in self.events if e.timestamp > t_start - 2.0]

        h = self.STRIP_H

        # Background
        bg_rect = pygame.Rect(x, y, width, h)
        pygame.draw.rect(surface, (25, 25, 30), bg_rect)
        pygame.draw.rect(surface, (50, 50, 60), bg_rect, 1)

        # Time markers (every 5s)
        for sec in range(0, int(self.WINDOW_SEC) + 1, 5):
            tx = x + int((sec / self.WINDOW_SEC) * width)
            pygame.draw.line(surface, (45, 45, 55), (tx, y), (tx, y + h), 1)
            label = f"-{int(self.WINDOW_SEC - sec)}s"
            surf = font.render(label, True, (60, 60, 70))
            surface.blit(surf, (tx + 2, y + h - 12))

        # Draw events
        for event in self.events:
            elapsed = event.timestamp - t_start
            if elapsed < 0:
                continue
            ex = x + int((elapsed / self.WINDOW_SEC) * width)

            if event.kind == "mood":
                # Colored block
                rect = pygame.Rect(ex - 2, y + 2, 5, h // 2 - 2)
                pygame.draw.rect(surface, event.color, rect)
            elif event.kind == "conv":
                # Colored tick
                pygame.draw.line(
                    surface, event.color, (ex, y + h // 2), (ex, y + h - 2), 2
                )
            elif event.kind == "gesture":
                # White dot
                pygame.draw.circle(surface, event.color, (ex, y + h // 2), 2)
            elif event.kind == "guardrail":
                # Red triangle marker
                pygame.draw.polygon(
                    surface,
                    event.color,
                    [(ex, y + 2), (ex - 3, y + 8), (ex + 3, y + 8)],
                )
