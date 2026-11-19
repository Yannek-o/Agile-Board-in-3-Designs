def percent(part: int, whole: int) -> int:
    """Whole-number share of ``part`` in ``whole``; 0 when ``whole`` is 0."""
    return int(part * 100 / whole) if whole else 0
