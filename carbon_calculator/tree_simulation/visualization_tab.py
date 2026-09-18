# SPDX-License-Identifier: MIT
"""Carbon1 오른쪽 결과 탭에 삽입되는 지역별 3D 시각화 QWidget."""
from __future__ import annotations

from typing import Callable

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QCursor
from PyQt5.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QSlider, QToolTip, QVBoxLayout,
    QWidget,
)
from pyvistaqt import QtInteractor

from ..i18n import environment_name, species_name, tr
from ..ui_scale import pt, px
from ..typography import HEADING_PT
from .models import RegionVisualizationSnapshot
from .detail_dialog import VegetationDetailDialog
from .inspection import inspect_instance
from .renderer import VegetationRenderer


SnapshotProvider = Callable[[], RegionVisualizationSnapshot]
FingerprintProvider = Callable[[], str]


class VegetationVisualizationTab(QWidget):
    year_changed = pyqtSignal(int)

    @property
    def snapshot(self) -> RegionVisualizationSnapshot | None:
        return self._snapshot
    def __init__(self, snapshot_provider: SnapshotProvider,
                 fingerprint_provider: FingerprintProvider, year_slider: QSlider, parent=None):
        super().__init__(parent)
        self.year_slider = year_slider
        self._snapshot_provider = snapshot_provider
        self._fingerprint_provider = fingerprint_provider
        self._snapshot: RegionVisualizationSnapshot | None = None
        self._mouse_press_position: tuple[int, int] | None = None
        self._detail_dialogs: list[VegetationDetailDialog] = []
        self._build_ui()
        self._play_timer = QTimer(self)
        self._play_timer.setInterval(450)
        self._play_timer.timeout.connect(self._advance_year)
        self._sync_timer = QTimer(self)
        self._sync_timer.setInterval(900)
        self._sync_timer.timeout.connect(self._check_stale)
        self._sync_timer.start()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(5)

        self.region_label = QLabel(tr("시각화를 새로고침하세요."))
        font = self.region_label.font(); font.setPointSize(pt(HEADING_PT)); font.setBold(True)
        self.region_label.setFont(font)
        self.region_label.setStyleSheet("color: #246B43; padding: 3px;")
        root.addWidget(self.region_label)

        self.plotter = QtInteractor(self, auto_update=False)
        self.plotter.setMinimumHeight(px(300))
        self.plotter.set_background("#EEF3F0")
        # 지면의 Z축을 항상 위쪽으로 유지한다. 기본 trackball 방식에서 가능한
        # 카메라 roll을 제거해 화면이 좌우로 기울어지는 것을 방지한다.
        self.plotter.enable_terrain_style(mouse_wheel_zooms=True, shift_pans=True)
        self.renderer = VegetationRenderer(self.plotter)
        self.plotter.iren.add_observer("MouseMoveEvent", self._on_3d_mouse_move)
        self.plotter.iren.add_observer("LeftButtonPressEvent", self._on_3d_mouse_press)
        self.plotter.iren.add_observer("LeftButtonReleaseEvent", self._on_3d_mouse_release)
        root.addWidget(self.plotter, 1)

        controls = QFrame()
        row = QHBoxLayout(controls); row.setContentsMargins(4, 2, 4, 2)
        self.play_btn = QPushButton(tr("재생"))
        self.pause_btn = QPushButton(tr("일시정지"))
        self.refresh_btn = QPushButton(tr("새로고침"))
        self.play_btn.clicked.connect(self.play)
        self.pause_btn.clicked.connect(self.pause)
        self.refresh_btn.clicked.connect(self.refresh_snapshot)
        row.addWidget(self.play_btn); row.addWidget(self.pause_btn)
        self.year_slider.valueChanged.connect(self._on_year_changed)
        self.year_label = QLabel(tr("현재: 0년"))
        row.addWidget(self.year_label)
        row.addStretch(1)
        row.addWidget(self.refresh_btn)
        root.addWidget(controls)

        self.summary_label = QLabel(tr("총 탄소저장량: 0.00 kgC · 교목 0주 / 관목 0주"))
        self.summary_label.setAlignment(Qt.AlignCenter)
        self.summary_label.setStyleSheet(
            "background: #FFFFFF; border: 1px solid #D8DEE4; border-radius: 5px; padding: 5px;"
        )
        root.addWidget(self.summary_label)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("color: #B05A2B; padding: 1px 4px;")
        self.status_label.hide()
        root.addWidget(self.status_label)

    def refresh_snapshot(self) -> None:
        self.pause()
        try:
            snapshot = self._snapshot_provider()
        except Exception as exc:  # 사용자에게 3D 계층 오류를 알리고 기존 앱은 유지
            self.status_label.setText(
                tr("시각화 갱신 실패: {error}").format(error=exc))
            self.status_label.show()
            return
        self._snapshot = snapshot
        self.region_label.setText(
            tr("지역: {name} · 대상지 유형: {env} · 면적: {w:g} × {h:g} m").format(
                name=snapshot.region_name or tr("지역"),
                env=environment_name(snapshot.environment),
                w=snapshot.area_w, h=snapshot.area_h,
            )
            + f"  ({snapshot.area_w * snapshot.area_h:,.0f} m²)"
        )
        if not snapshot.instances:
            self.plotter.clear_actors()
            self.renderer.clear()
            self.plotter.add_text(tr("표시할 유효 교목/관목 입력이 없습니다."), position="upper_left")
            self.status_label.setText(tr("항목을 추가한 뒤 계산하거나 새로고침하세요."))
            self.status_label.show()
        else:
            self.plotter.clear_actors()
            self.renderer.set_snapshot(snapshot)
            self.status_label.clear()
            self.status_label.hide()
        self._on_year_changed(self.year_slider.value())

    def _check_stale(self) -> None:
        if not self.isVisible():
            return
        try:
            fingerprint = self._fingerprint_provider()
        except Exception:
            return
        if self._snapshot is None or fingerprint != self._snapshot.input_fingerprint:
            self.status_label.setText(tr("입력이 변경되어 최신 상태로 시각화를 갱신합니다."))
            self.refresh_snapshot()

    def _on_year_changed(self, year: int) -> None:
        self.year_label.setText(tr("현재: {year}년").format(year=year))
        if self._snapshot is None:
            return
        self.renderer.update_year(year)
        carbon = float(self._snapshot.total_carbon_by_year_kgc[year])
        self.summary_label.setText(
            tr("총 탄소저장량: {carbon:,.2f} kgC · 교목 {trees:,}주 / 관목 {shrubs:,}주")
            .format(carbon=carbon, trees=self._snapshot.tree_count,
                    shrubs=self._snapshot.shrub_count)
        )
        self.year_changed.emit(year)

    def _event_position(self) -> tuple[int, int]:
        x, y = self.plotter.interactor.GetEventPosition()
        return int(x), int(y)

    def _inspection_at(self, x: int, y: int):
        if self._snapshot is None:
            return None
        instance_id = self.renderer.pick_instance(x, y)
        if instance_id is None:
            return None
        return inspect_instance(self._snapshot, instance_id, self.year_slider.value())

    def _on_3d_mouse_move(self, *_args) -> None:
        info = self._inspection_at(*self._event_position())
        if info is None:
            QToolTip.hideText()
            return
        diameter_name = "DBH" if info.kind == "tree" else "RCD"
        QToolTip.showText(
            QCursor.pos(),
            f"{species_name(info.species)}\n"
            f"{diameter_name}: {info.diameter:,.2f} {info.diameter_unit}\n"
            + tr("탄소저장량: {carbon:,.4f} kgC/주\n클릭하면 상세 정보를 표시합니다.")
            .format(carbon=info.carbon_kgc),
            self.plotter,
        )

    def _on_3d_mouse_press(self, *_args) -> None:
        self._mouse_press_position = self._event_position()

    def _on_3d_mouse_release(self, *_args) -> None:
        end = self._event_position()
        start = self._mouse_press_position
        self._mouse_press_position = None
        if start is None or abs(end[0] - start[0]) + abs(end[1] - start[1]) > 5:
            return  # 카메라를 회전한 drag는 개체 클릭으로 취급하지 않는다.
        info = self._inspection_at(*end)
        if info is None:
            return
        dialog = VegetationDetailDialog(info, self)
        self._detail_dialogs.append(dialog)
        dialog.finished.connect(lambda _result, d=dialog: self._detail_dialogs.remove(d))
        dialog.show()

    def play(self) -> None:
        if self._snapshot is None:
            self.refresh_snapshot()
        if self.year_slider.value() >= 30:
            self.year_slider.setValue(0)
        self._play_timer.start()

    def pause(self) -> None:
        if hasattr(self, "_play_timer"):
            self._play_timer.stop()

    def _advance_year(self) -> None:
        value = self.year_slider.value()
        if value >= 30:
            self.pause()
            return
        next_value = value + 1
        self.year_slider.setValue(next_value)
        if next_value >= 30:
            self.pause()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._check_stale()

    def hideEvent(self, event) -> None:
        self.pause()
        super().hideEvent(event)

    def closeEvent(self, event) -> None:
        self.pause()
        self._sync_timer.stop()
        self.renderer.clear()
        self.plotter.close()
        super().closeEvent(event)
