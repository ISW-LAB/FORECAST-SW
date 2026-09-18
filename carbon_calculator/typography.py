# SPDX-License-Identifier: MIT
"""Shared, dependency-free typography for assessment and library-manager UIs.

Every point size in the application is defined here — the assessment window,
the library manager, the 3-D visualisation tab, the matplotlib charts, the
Excel chart images and the updater all read from this table, so a role
(body, heading, value, …) has one size everywhere.

Sizes are deliberately larger than a typical desktop UI: screenshots of this
software are placed in manuscripts, where the figure is reduced to column
width and small type becomes unreadable.

To enlarge (or shrink) every size at once — UI, charts and exported images —
change :data:`TYPE_SCALE` only; nothing else needs to be touched.
"""

# 전역 배율. 1.0 = 아래 설계 크기 그대로.
# 논문 도판을 더 크게 뽑아야 하면 이 값만 올린다 (예: 1.15).
TYPE_SCALE = 1.0

# ── UI 점 크기 (설계 기준 해상도 1920×1080, ui_scale = 1.0) ──────────────
CAPTION_PT = 16   # 로그·각주 등 보조 텍스트
SMALL_PT = 17     # 게이지 눈금값, 부제, 힌트
BODY_PT = 19      # 본문 = 애플리케이션 기본 폰트, 탭 라벨
HEADING_PT = 22   # 섹션 제목, 결과 테이블, 주 버튼
TITLE_PT = 24     # 창·대시보드 제목
VALUE_PT = 24     # 강조 수치 (총 탄소저장량 등)

# 축소 하한 — 작은 모니터에서도 이 크기 밑으로는 내려가지 않는다.
# 너무 높이면 저해상도 노트북에서 역할 간 크기 차이가 사라지므로 13pt 로 둔다.
MINIMUM_PT = 13

# ── matplotlib 그래프 (앱 내 캔버스 + Excel 내보내기 이미지 공통) ────────
# 주의: 그래프 글자는 UI 글자보다 화면에서 더 크게 보인다(캔버스 dpi 100 기준
# 1pt ≈ 1.39px, Qt 는 96dpi 기준 1pt ≈ 1.33px). 앱 안의 그래프 패널은 높이가
# 제한적이므로, 더 키우면 축·범례가 그림 영역을 잠식해 그래프가 작아 보인다.
PLOT_BODY_PT = 22        # font.size
PLOT_TITLE_PT = 24       # axes.titlesize
PLOT_LABEL_PT = 22       # axes.labelsize
PLOT_TICK_PT = 19        # x/ytick.labelsize
PLOT_LEGEND_PT = 18      # legend.fontsize
PLOT_ANNOTATION_PT = 16  # 막대 위 수치, 파이 조각 라벨
PLOT_MESSAGE_PT = 18     # "데이터 없음" 등 캔버스 안내 문구

# ── 3-D 시각화 (VTK/PyVista 축 글자) ────────────────────────────────────
AXIS_LABEL_PT = 20
AXIS_TITLE_PT = 22


def font_family(language: str) -> str:
    return "Arial" if language == "en" else "Malgun Gothic"


def scaled_point_size(size: float, scale: float) -> int:
    """설계 크기를 화면 스케일과 전역 배율에 맞춘 정수 point 로 변환."""
    floor = max(1, round(MINIMUM_PT * TYPE_SCALE))
    return max(floor, round(size * scale * TYPE_SCALE))
