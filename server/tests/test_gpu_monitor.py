import logging

from app import gpu_monitor


def setup_function():
    gpu_monitor._reset_for_tests()


def test_counts_cuda_oom_in_message_and_traceback():
    handler = gpu_monitor.OomCounter()
    log = logging.getLogger("test.gpu")
    log.addHandler(handler)
    try:
        log.error("CUDA failed with error out of memory")
        try:
            raise RuntimeError("CUDA failed with error out of memory")
        except RuntimeError:
            log.exception("STT preload failed; it will load on first use")
        log.error("ran out of memory in the dashboard cache")  # not a GPU OOM
        log.info("all fine")
    finally:
        log.removeHandler(handler)
    snap = gpu_monitor.snapshot()
    assert snap["oom_count"] == 2
    assert snap["last_oom"]["message"].startswith("STT preload failed")


def test_low_free_flag(monkeypatch):
    monkeypatch.setattr(
        gpu_monitor,
        "_query_nvidia_smi",
        lambda: {"free_gb": 0.3, "used_gb": 23.7, "total_gb": 24.0},
    )
    snap = gpu_monitor.snapshot()
    assert snap["low_free"] is True
    assert snap["free_gb"] == 0.3


def test_no_nvidia_smi(monkeypatch):
    monkeypatch.setattr(gpu_monitor, "_query_nvidia_smi", lambda: None)
    snap = gpu_monitor.snapshot()
    assert snap["free_gb"] is None and snap["low_free"] is False


def test_cache(monkeypatch):
    calls = []

    def fake():
        calls.append(1)
        return {"free_gb": 5.0, "used_gb": 19.0, "total_gb": 24.0}

    monkeypatch.setattr(gpu_monitor, "_query_nvidia_smi", fake)
    gpu_monitor.gpu_memory(now=100.0)
    gpu_monitor.gpu_memory(now=102.0)
    gpu_monitor.gpu_memory(now=106.0)
    assert len(calls) == 2
