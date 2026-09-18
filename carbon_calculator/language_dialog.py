# SPDX-License-Identifier: MIT
# -*- coding: utf-8 -*-
"""시작 시 표시 언어 선택 대화상자.

저장된 언어가 없을 때(최초 실행) 한 번 뜬다. 이후에는 저장값을 쓰고,
[도움말]→[언어] 메뉴에서 바꿀 수 있다. 이 창만은 두 언어를 함께 보여 준다.
"""
from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog, QDialogButtonBox, QLabel, QRadioButton, QVBoxLayout,
)

from .i18n import LANG_EN, LANG_KO
from .typography import HEADING_PT
from .ui_scale import pt


class LanguageDialog(QDialog):
    """한국어/English 선택. `chosen()` 으로 선택된 코드를 얻는다."""

    def __init__(self, current: str = LANG_KO, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Language")
        self.setModal(True)
        self.setMinimumWidth(460)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(10)

        title = QLabel("Select the display language.")
        font = title.font(); font.setPointSize(pt(HEADING_PT)); font.setBold(True)
        title.setFont(font)
        layout.addWidget(title)

        self.ko_radio = QRadioButton("Korean — species labelled with Korean common names")
        self.en_radio = QRadioButton("English — species labelled with scientific names")
        (self.en_radio if current == LANG_EN else self.ko_radio).setChecked(True)
        layout.addWidget(self.ko_radio)
        layout.addWidget(self.en_radio)

        note = QLabel(
            "English mode renders the interface, figures and Excel output in English, "
            "with species shown as scientific names (e.g. Pinus densiflora) for direct "
            "use in manuscripts."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #5A6B60; padding-top: 4px;")
        layout.addWidget(note)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok)
        buttons.button(QDialogButtonBox.Ok).setText("OK")
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

    def chosen(self) -> str:
        return LANG_EN if self.en_radio.isChecked() else LANG_KO
