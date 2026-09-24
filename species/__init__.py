"""Registered species modules are named for their eventual .silk stems."""

from .hortophora import build, SPEC

SPECIES = {SPEC.id: build}
