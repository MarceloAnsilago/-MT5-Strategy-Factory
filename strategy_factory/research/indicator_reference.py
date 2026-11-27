"""Reference indicators for offline research on chronological bars."""

from math import isfinite
from numbers import Real


def atr(high, low, close, period):
    """Return Wilder ATR with None during warmup, oldest bar first.

    Raise ValueError for invalid periods, series lengths or price values.
    """
    if isinstance(period, bool) or not isinstance(period, int) or period < 1:
        raise ValueError("period must be a positive integer")
    if not len(high) == len(low) == len(close):
        raise ValueError("price series must have equal lengths")

    result = []
    previous_close = None
    average = 0.0
    for index, prices in enumerate(zip(high, low, close)):
        if any(isinstance(price, bool) or not isinstance(price, Real)
               or not isfinite(price) for price in prices):
            raise ValueError(f"invalid price at index {index}")
        upper, lower, closing = map(float, prices)
        if upper < lower:
            raise ValueError(f"high below low at index {index}")
        true_range = upper - lower
        if previous_close is not None:
            true_range = max(true_range, abs(upper - previous_close),
                             abs(lower - previous_close))
        if not isfinite(true_range):
            raise ValueError(f"non-finite true range at index {index}")

        if index < period:
            average += (true_range - average) / (index + 1)
        else:
            average += (true_range - average) / period
        result.append(average if index >= period - 1 else None)
        previous_close = closing
    return result
