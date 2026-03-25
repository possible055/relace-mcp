from collections.abc import Iterable, Sequence


def merge_ranges(ranges: Iterable[tuple[int, int]]) -> list[tuple[int, int]]:
    sorted_ranges = sorted(ranges, key=lambda value: (value[0], value[1]))
    if not sorted_ranges:
        return []

    merged: list[tuple[int, int]] = [sorted_ranges[0]]
    for start, end in sorted_ranges[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end + 1:
            merged[-1] = (last_start, max(last_end, end))
            continue
        merged.append((start, end))
    return merged


def normalize_line_ranges(ranges: Iterable[Sequence[object]]) -> list[tuple[int, int]]:
    normalized: list[tuple[int, int]] = []
    for value in ranges:
        if (
            isinstance(value, (list, tuple))
            and len(value) == 2
            and isinstance(value[0], int)
            and isinstance(value[1], int)
            and value[0] > 0
            and value[1] >= value[0]
        ):
            normalized.append((value[0], value[1]))
    return merge_ranges(normalized)


def intersection_length(a: list[tuple[int, int]], b: list[tuple[int, int]]) -> int:
    i = 0
    j = 0
    total = 0
    while i < len(a) and j < len(b):
        a_start, a_end = a[i]
        b_start, b_end = b[j]
        start = max(a_start, b_start)
        end = min(a_end, b_end)
        if start <= end:
            total += end - start + 1

        if a_end < b_end:
            i += 1
        else:
            j += 1
    return total
