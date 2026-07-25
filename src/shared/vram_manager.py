"""VRAM management — monitors GPU memory and frees cache under pressure."""

from loguru import logger

VRAM_WARNING_THRESHOLD = 0.85
VRAM_CRITICAL_THRESHOLD = 0.95


def get_vram_stats() -> dict:
    """Return current VRAM usage stats."""
    try:
        import torch

        if not torch.cuda.is_available():
            return {"available": False}
        props = torch.cuda.get_device_properties(0)
        allocated = torch.cuda.memory_allocated()
        total = props.total_memory
        return {
            "available": True,
            "allocated_mb": allocated // (1024**2),
            "total_mb": total // (1024**2),
            "free_mb": (total - allocated) // (1024**2),
            "utilization": allocated / total if total > 0 else 0,
        }
    except Exception:
        return {"available": False}


def free_vram_cache() -> None:
    """Release PyTorch VRAM cache back to the OS."""
    try:
        import torch

        if torch.cuda.is_available():
            before = torch.cuda.memory_reserved()
            torch.cuda.empty_cache()
            after = torch.cuda.memory_reserved()
            freed_mb = (before - after) // (1024**2)
            if freed_mb > 0:
                logger.info(f"VRAM: freed {freed_mb}MB cache")
    except Exception as e:
        logger.debug(f"VRAM: cache free failed: {e}")


def check_vram_pressure() -> str:
    """Returns 'ok', 'warning', or 'critical'."""
    stats = get_vram_stats()
    if not stats.get("available"):
        return "ok"
    util = stats["utilization"]
    if util >= VRAM_CRITICAL_THRESHOLD:
        logger.warning(f"VRAM: CRITICAL — {util:.1%} used ({stats['free_mb']}MB free)")
        free_vram_cache()
        return "critical"
    if util >= VRAM_WARNING_THRESHOLD:
        logger.warning(f"VRAM: WARNING — {util:.1%} used ({stats['free_mb']}MB free)")
        return "warning"
    return "ok"
