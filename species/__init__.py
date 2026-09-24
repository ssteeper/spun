"""Registered species modules are named for their eventual .silk stems."""

from . import argiope, golden, hortophora

SPECIES = {module.SPEC.id: module.build for module in (golden, argiope, hortophora)}
