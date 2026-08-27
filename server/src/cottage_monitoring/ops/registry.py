"""Ops registry: one registration per operation, both faces read from here."""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import HTTPException

from cottage_monitoring.ops.spec import OpSpec


class OpsRegistry:
    def __init__(self) -> None:
        self._ops: dict[str, OpSpec] = {}

    def register(self, spec: OpSpec) -> OpSpec:
        if spec.name in self._ops:
            raise ValueError(f"Op '{spec.name}' is already registered")
        self._ops[spec.name] = spec
        return spec

    def get(self, name: str) -> OpSpec:
        spec = self._ops.get(name)
        if spec is None:
            raise HTTPException(status_code=404, detail=f"Unknown op '{name}'")
        return spec

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._ops))

    def all(self) -> tuple[OpSpec, ...]:
        return tuple(self._ops[name] for name in self.names())

    def __contains__(self, name: object) -> bool:
        return name in self._ops

    def __iter__(self) -> Iterator[OpSpec]:
        return iter(self.all())

    def __len__(self) -> int:
        return len(self._ops)


registry = OpsRegistry()


def register(spec: OpSpec) -> OpSpec:
    return registry.register(spec)


def get(name: str) -> OpSpec:
    return registry.get(name)


def all_ops() -> tuple[OpSpec, ...]:
    return registry.all()


def op_names() -> tuple[str, ...]:
    return registry.names()
