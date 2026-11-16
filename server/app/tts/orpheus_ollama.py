"""Orpheus on llama.cpp (Ollama raw mode), a drop-in for the vLLM `OrpheusModel`.

Measured 2026-11-15 on the 3090 Ti: the community Q8_0 GGUF
(`hf.co/lex-au/Orpheus-3b-FT-Q8_0.gguf`) generates 182 audio tokens/s (2.17x real
time, first 28 tokens in ~190 ms) against 97 tok/s (1.15x) for bf16 on vLLM, in
4.6 GB of VRAM instead of 7.6 GB; Whisper read every test clip back exactly.

Same interface as `orpheus_tts.OrpheusModel.generate_speech`: a sync generator of
int16 PCM chunks at 24 kHz. The token -> audio step mirrors `orpheus_tts.decoder`
(SNAC over a sliding 28-token window, 7 new tokens per step).
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterator

import httpx

log = logging.getLogger(__name__)

_TOKEN = re.compile(r"<custom_token_(\d+)>")
# Orpheus prompt framing (start-of-human, text, end-of-text, end-of-human,
# start-of-AI, start-of-speech) as the decoded string of orpheus_tts's token ids.
_PROMPT = (
    "<custom_token_3><|begin_of_text|>{voice}: {text}<|eot_id|>"
    "<custom_token_4><custom_token_5><custom_token_1>"
)
_END_OF_SPEECH = "<custom_token_2>"


def audio_code(token_number: int, index: int) -> int:
    """Raw `<custom_token_N>` number -> SNAC code for the `index`-th audio token."""
    return token_number - 10 - (index % 7) * 4096


class OllamaOrpheus:
    def __init__(
        self,
        model: str,
        url: str,
        *,
        keep_alive: str = "60m",
        temperature: float = 0.6,
        top_p: float = 0.8,
        repetition_penalty: float = 1.3,
        max_tokens: int = 1500,
        timeout_s: float = 60.0,
    ) -> None:
        self.model = model
        self.url = url.rstrip("/")
        self.keep_alive = keep_alive
        self.options = {
            "temperature": temperature,
            "top_p": top_p,
            "repeat_penalty": repetition_penalty,
            "num_predict": max_tokens,
            "stop": [_END_OF_SPEECH],
        }
        self.timeout_s = timeout_s
        self._client = httpx.Client(timeout=timeout_s)

    def _tokens(self, prompt: str, voice: str | None) -> Iterator[int]:
        body = {
            "model": self.model,
            "prompt": _PROMPT.format(voice=voice or "tara", text=prompt),
            "raw": True,
            "stream": True,
            "keep_alive": self.keep_alive,
            "options": self.options,
        }
        with self._client.stream("POST", f"{self.url}/api/generate", json=body) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if not line:
                    continue
                d = json.loads(line)
                if d.get("error"):
                    raise RuntimeError(f"ollama: {d['error']}")
                for m in _TOKEN.finditer(d.get("response", "")):
                    yield int(m.group(1))
                if d.get("done"):
                    return

    def generate_speech(
        self, *, prompt: str, voice: str | None = None, request_id: str = ""
    ) -> Iterator[bytes]:
        from orpheus_tts.decoder import convert_to_audio  # loads SNAC on first use

        codes: list[int] = []
        for n in self._tokens(prompt, voice):
            code = audio_code(n, len(codes))
            if code <= 0:
                continue
            codes.append(code)
            if len(codes) % 7 == 0 and len(codes) > 27:
                pcm = convert_to_audio(codes[-28:], len(codes))
                if pcm:
                    yield pcm

    def warm(self) -> bool:
        """Load the model into VRAM; True if it produced audio tokens."""
        try:
            return any(True for _ in self._tokens("Hi!", "tara"))
        except Exception:
            log.warning("ollama orpheus warm-up failed", exc_info=True)
            return False

    def shutdown(self) -> None:
        self._client.close()
