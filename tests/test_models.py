"""Unit tests for the geometry and text primitives everything else rests on."""

from __future__ import annotations

from verso.models import BBox, levenshtein_ratio, truncate_excerpt


def test_bbox_normalization():
    b = BBox(10, 20, 5, 8)          # reversed corners
    assert b.x0 == 5 and b.x1 == 10
    assert b.top == 8 and b.bottom == 20


def test_iou_identical_and_disjoint():
    a = BBox(0, 0, 10, 10)
    assert a.iou(BBox(0, 0, 10, 10)) == 1.0
    assert a.iou(BBox(20, 20, 30, 30)) == 0.0


def test_iou_half_overlap():
    a = BBox(0, 0, 10, 10)
    b = BBox(5, 0, 15, 10)          # 50% overlap area 50, union 150
    assert abs(a.iou(b) - (50 / 150)) < 1e-9


def test_contains_with_pad():
    outer = BBox(0, 0, 100, 20)
    inner = BBox(2, 2, 98, 18)
    assert outer.contains(inner)
    assert not outer.contains(BBox(-5, 0, 50, 10))


def test_levenshtein_ratio():
    assert levenshtein_ratio("thirty days", "thirty days") == 1.0
    # "thirty" vs "three hundred" is a real substitution, low similarity
    assert levenshtein_ratio("thirty days", "three hundred days") < 0.6


def test_truncate_strips_control_chars_and_flags():
    text, trunc = truncate_excerpt("hello\x00\x07 world", limit=100)
    assert "\x00" not in text and "\x07" not in text
    assert not trunc
    long = "x" * 300
    _, trunc2 = truncate_excerpt(long, limit=120)
    assert trunc2
