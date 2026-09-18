# SPDX-License-Identifier: MIT
# -*- coding: utf-8 -*-
"""
모니터 크기·해상도에 반응하는 UI 스케일링 유틸리티.

핵심 아이디어
-------------
- 설계 기준 해상도(``_REF_W`` × ``_REF_H``)에서 100%(scale=1.0) 로 보이도록 만들고,
  실제 모니터의 사용 가능 영역이 더 작으면 위젯·폰트·창 크기를 비례 축소한다.
- 기준보다 큰 모니터에서는 약간만(최대 1.5배) 확대한다.

사용 순서
---------
1. ``enable_high_dpi()`` 를 **QApplication 생성 전에** 호출 (고해상도 자동 스케일링).
2. QApplication 생성 후 ``ui_scale(app)`` 로 스케일 배수를 얻어
   폰트/테마/창 크기에 반영한다.
"""
from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QWidget
from .typography import scaled_point_size


# 설계 기준 해상도 (이 해상도의 사용 가능 영역에서 scale = 1.0)
_REF_W = 1920
_REF_H = 1080

# 스케일 허용 범위 (작은 노트북에서도 과도하게 작아지지 않고,
# 초고해상도에서도 과도하게 커지지 않도록 제한)
_SCALE_MIN = 0.70
_SCALE_MAX = 1.50

_cached_scale: float | None = None


def enable_high_dpi() -> None:
    """고해상도(High-DPI) 디스플레이 지원 활성화. **QApplication 생성 전** 호출."""
    # 분수 배율(예: 125%, 150%) 모니터에서도 또렷하게 렌더링되도록 PassThrough 적용.
    try:
        policy = Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        QApplication.setHighDpiScaleFactorRoundingPolicy(policy)
    except Exception:
        pass
    for attr in ("AA_EnableHighDpiScaling", "AA_UseHighDpiPixmaps"):
        flag = getattr(Qt, attr, None)
        if flag is not None:
            try:
                QApplication.setAttribute(flag, True)
            except Exception:
                pass


def _available_geometry():
    app = QApplication.instance()
    if app is None:
        return None
    screen = app.primaryScreen()
    if screen is None:
        return None
    return screen.availableGeometry()


def ui_scale(app: QApplication | None = None) -> float:
    """주 모니터의 사용 가능 영역 기준 UI 스케일 배수 (0.70 ~ 1.50). 최초 1회 계산 후 캐시."""
    global _cached_scale
    if _cached_scale is not None:
        return _cached_scale

    scale = 1.0
    geo = _available_geometry()
    if geo is not None and geo.width() > 0 and geo.height() > 0:
        scale = min(geo.width() / _REF_W, geo.height() / _REF_H)
    _cached_scale = max(_SCALE_MIN, min(_SCALE_MAX, scale))
    return _cached_scale


def reset_scale_cache() -> None:
    """(테스트용) 캐시된 스케일 초기화."""
    global _cached_scale
    _cached_scale = None


def px(value: float) -> int:
    """픽셀 값을 현재 스케일로 변환 (최소 1)."""
    return max(1, round(value * ui_scale()))


def pt(point_size: float) -> int:
    """Scale text while retaining a readable 12pt minimum."""
    return scaled_point_size(point_size, ui_scale())


def apply_window_size(window: QWidget,
                      wfrac: float = 0.82,
                      hfrac: float = 0.86,
                      min_w: int = 1100,
                      min_h: int = 680) -> None:
    """
    창 크기를 사용 가능한 화면의 비율(wfrac × hfrac)로 설정하고 화면 중앙에 배치.

    - 작은 화면에서는 최소 크기를 화면을 넘지 않도록 자동 축소한다.
    - 큰 화면에서는 ``min_w/min_h`` 이상으로 보장한다.
    """
    geo = _available_geometry()
    if geo is None:
        window.resize(max(min_w, 1280), max(min_h, 800))
        return

    avail_w, avail_h = geo.width(), geo.height()

    # 최소 크기는 화면을 넘지 않게 제한
    eff_min_w = min(min_w, avail_w)
    eff_min_h = min(min_h, avail_h)
    window.setMinimumSize(eff_min_w, eff_min_h)

    w = max(eff_min_w, min(int(avail_w * wfrac), avail_w))
    h = max(eff_min_h, min(int(avail_h * hfrac), avail_h))
    window.resize(w, h)

    # 사용 가능 영역 기준 중앙 정렬
    x = geo.x() + (avail_w - w) // 2
    y = geo.y() + (avail_h - h) // 2
    window.move(x, y)


def apply_dialog_size(dialog: QWidget, width: int, height: int,
                      margin: int = 48) -> None:
    """다이얼로그 크기를 스케일에 맞추고, 화면을 넘지 않도록 클램프."""
    s = ui_scale()
    w = round(width * s)
    h = round(height * s)
    geo = _available_geometry()
    if geo is not None:
        w = min(w, geo.width() - margin)
        h = min(h, geo.height() - margin)
    dialog.resize(max(360, w), max(320, h))
