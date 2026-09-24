import re


def _key(name: str) -> tuple[list[str | int], str]:
    parts = re.split(r"(\d+)", name.casefold())
    return [int(p) if i % 2 else p for i, p in enumerate(parts)], name


def natural_sort(names: list[str]) -> list[str]:
    return sorted(names, key=_key)
