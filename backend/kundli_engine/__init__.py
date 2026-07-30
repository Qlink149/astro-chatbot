"""Deterministic Vedic chart engine. The ONLY thing allowed to calculate a chart."""

__all__ = ["BirthDetails", "compute_chart"]


def __getattr__(name: str):
    if name in ("BirthDetails", "compute_chart"):
        from kundli_engine.engine import BirthDetails, compute_chart

        return BirthDetails if name == "BirthDetails" else compute_chart
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
