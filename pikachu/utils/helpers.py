"""pikachu/utils/helpers.py — GPU detection and path utilities."""

import os
import ctypes
from pikachu.utils.logger import get_logger

log = get_logger(__name__)


def get_gpu_vram_mb() -> int:
    """
    Return the total VRAM of the primary GPU in megabytes.
    Returns 0 if no GPU is detected or pynvml is not installed.
    """
    # ── Try pynvml (NVIDIA) ───────────────────────────────────────────────────
    try:
        import pynvml
        pynvml.nvmlInit()
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        info   = pynvml.nvmlDeviceGetMemoryInfo(handle)
        mb     = info.total // (1024 * 1024)
        log.info(f"GPU VRAM detected via pynvml: {mb} MB")
        return mb
    except Exception:
        pass

    # ── Try DXGI via ctypes (works without pynvml) ────────────────────────────
    try:
        # Use Windows DXGI adapter to query dedicated video memory
        # This is a best-effort heuristic via the DirectX Diagnostic Tool registry key
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\DirectX",
        )
        vram_bytes, _ = winreg.QueryValueEx(key, "MaxTextureDimension")
        # MaxTextureDimension isn't VRAM — skip this, return 0 as fallback
        winreg.CloseKey(key)
    except Exception:
        pass

    log.info("GPU VRAM could not be detected — assuming CPU-only mode.")
    return 0


def get_gpu_utilization() -> int:
    """
    Return the primary GPU utilization percentage (0-100).
    Returns 0 if no GPU is detected or pynvml is not installed.
    """
    try:
        import pynvml
        pynvml.nvmlInit()
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        rates  = pynvml.nvmlDeviceGetUtilizationRates(handle)
        return int(rates.gpu)
    except Exception:
        return 0


def classify_gpu(vram_mb: int) -> str:
    """
    Classify GPU capability based on VRAM.

    Returns:
        "none"  — no GPU / not enough VRAM for even the big model
        "low"   — enough for Mistral 7B (~6 GB)
        "high"  — enough for Mistral NeMo 12B (~12 GB)
    """
    from pikachu import config as cfg
    if vram_mb >= cfg.GPU_HIGH_VRAM_MB:
        return "high"
    if vram_mb >= cfg.GPU_LOW_VRAM_MB:
        return "low"
    return "none"


def asset_path(filename: str) -> str:
    """Return the absolute path to an asset file."""
    from pikachu import config as cfg
    return os.path.join(cfg.ASSETS_DIR, filename)
