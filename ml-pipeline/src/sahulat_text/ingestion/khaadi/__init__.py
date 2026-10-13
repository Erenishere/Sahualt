"""Khaadi v1 fixture adapter; evaluation data, never production vendor metadata."""

from .mapper import KhaadiMappingResult, map_khaadi_fixture
from .reader import KhaadiAuthority, load_khaadi_authority

__all__ = [
    "KhaadiAuthority",
    "KhaadiMappingResult",
    "load_khaadi_authority",
    "map_khaadi_fixture",
]
