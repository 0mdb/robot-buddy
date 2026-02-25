from __future__ import annotations

import logging

from supervisor.core import worker_manager as wm


def test_parse_worker_stderr_level_parses_prefixed_level() -> None:
    level, message = wm._parse_worker_stderr_level(
        "ERROR supervisor.workers.ear_worker: failed to load model"
    )
    assert level == logging.ERROR
    assert message == "supervisor.workers.ear_worker: failed to load model"


def test_log_worker_stderr_line_emits_warning_level(caplog) -> None:
    with caplog.at_level(logging.DEBUG, logger=wm.__name__):
        wm._log_worker_stderr_line(
            "ear", "WARNING supervisor.workers.ear_worker: mic socket not ready"
        )

    record = caplog.records[-1]
    assert record.levelno == logging.WARNING
    assert (
        record.getMessage()
        == "[ear] supervisor.workers.ear_worker: mic socket not ready"
    )


def test_log_worker_stderr_line_falls_back_to_info_for_unprefixed(caplog) -> None:
    with caplog.at_level(logging.DEBUG, logger=wm.__name__):
        wm._log_worker_stderr_line("ear", "Traceback (most recent call last):")

    record = caplog.records[-1]
    assert record.levelno == logging.INFO
    assert record.getMessage() == "[ear] Traceback (most recent call last):"
