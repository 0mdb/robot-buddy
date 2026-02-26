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


def test_log_worker_stderr_line_traceback_inherits_previous_error_level(caplog) -> None:
    with caplog.at_level(logging.DEBUG, logger=wm.__name__):
        inherited_level, traceback_active = wm._log_worker_stderr_line_with_context(
            "ear",
            "ERROR supervisor.workers.ear_worker: VAD inference error",
        )
        inherited_level, traceback_active = wm._log_worker_stderr_line_with_context(
            "ear",
            "Traceback (most recent call last):",
            inherited_level=inherited_level,
            traceback_active=traceback_active,
        )
        inherited_level, traceback_active = wm._log_worker_stderr_line_with_context(
            "ear",
            '  File "/path/worker.py", line 42, in _check_vad',
            inherited_level=inherited_level,
            traceback_active=traceback_active,
        )
        wm._log_worker_stderr_line_with_context(
            "ear",
            "ValueError: boom",
            inherited_level=inherited_level,
            traceback_active=traceback_active,
        )

    assert [r.levelno for r in caplog.records[-4:]] == [
        logging.ERROR,
        logging.ERROR,
        logging.ERROR,
        logging.ERROR,
    ]
    assert caplog.records[-3].getMessage() == "[ear] Traceback (most recent call last):"
    assert (
        'File "/path/worker.py", line 42, in _check_vad'
        in caplog.records[-2].getMessage()
    )
    assert caplog.records[-1].getMessage() == "[ear] ValueError: boom"


def test_log_worker_stderr_line_falls_back_to_info_for_unrelated_unprefixed(
    caplog,
) -> None:
    with caplog.at_level(logging.DEBUG, logger=wm.__name__):
        inherited_level, traceback_active = wm._log_worker_stderr_line_with_context(
            "ear", "ERROR supervisor.workers.ear_worker: something failed"
        )
        wm._log_worker_stderr_line_with_context(
            "ear",
            "unprefixed status line",
            inherited_level=inherited_level,
            traceback_active=traceback_active,
        )

    record = caplog.records[-1]
    assert record.levelno == logging.INFO
    assert record.getMessage() == "[ear] unprefixed status line"
