"""Test-wide setup."""

import os

# app/config.py loads the repo's .env, which may turn voice capture on: tests must never
# write turn audio or voiceprints to the real data directory.
os.environ["VOICE_CAPTURE"] = "0"
os.environ["VOICE_ID"] = "0"
