#!/usr/bin/env python3
"""Roland-style Linux GUI for the verified BRIDGE CAST ONE MIDI controls."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
import time

from PyQt6.QtCore import Qt, QTimer, QSize
from PyQt6.QtGui import QColor, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout,
    QLabel, QMainWindow, QMenuBar, QMessageBox, QPushButton, QScrollArea, QSlider,
    QStackedWidget, QVBoxLayout, QWidget,
)

from bridgecast_protocol import (
    BridgeCastOne, CHANNELS, LINE_OUT_MODES, MIC_FX_LIMITS, OUTPUT_LEVELS,
    OUTPUT_MUTES, PERSONAL_FADERS, PERSONAL_MUTES, STREAM_FADERS, STREAM_MUTES,
)
ASSETS = Path(__file__).resolve().parent / "assets"
APP_VERSION = "0.1.0"
COLORS = ("#ed4654", "#ffbf24", "#38bf79", "#3d9cff", "#ddb565", "#73a8f8", "#b992db")
FEATURED_COLORS = {0: "#66676a", 2: "#00a7f5", 3: "#a900df"}
FEATURED_SOURCES = {0: "MIC", 2: "CHAT", 3: "MUSIC"}
NAV_ICONS = {
    "HOME": "home", "MIC SETUP": "mic-setup", "MIC CLEANUP": "mic-cleanup",
    "VOICE TRANSFORMER": "voice-transformer", "GAME (USB)": "game", "CHAT": "chat",
    "OUTPUT": "output", "PROFILE": "profile", "SYSTEM": "system", "BGM CAST": "bgm",
}
LOW_CUT_FREQS = ("Flat", "20 Hz", "25 Hz", "31.5 Hz", "40 Hz", "50 Hz", "63 Hz", "80 Hz",
                 "100 Hz", "125 Hz", "160 Hz", "200 Hz", "250 Hz", "315 Hz", "400 Hz", "500 Hz")
COMP_RATIOS = ("1:1", "1.12:1", "1.25:1", "1.4:1", "1.6:1", "1.8:1", "2:1", "2.5:1",
               "3.2:1", "4:1", "5.6:1", "8:1", "16:1", "∞:1")
RELEASE_MS = (50, 60, 80, 100, 130, 160, 200, 250, 320, 400, 500, 640, 800,
              1000, 1250, 1600, 2000, 2500, 3200, 4000, 5000)
def indexed(values, value):
    return values[value] if 0 <= value < len(values) else str(value)


MIC_FORMAT = {
    0x02: lambda value: indexed(LOW_CUT_FREQS, value),
    0x12: lambda value: f"{value - 96} dB",
    0x22: lambda value: str(value + 1),
    0x72: lambda value: f"{value * 10} ms",
    0x74: lambda value: f"{indexed(RELEASE_MS, value)} ms",
    0x76: lambda value: f"{value * 3 - 48} dB",
    0x78: lambda value: indexed(COMP_RATIOS, value),
    0x7A: lambda value: f"+{value} dB",
}

STYLE = """
QMainWindow, QWidget { background: #050505; color: #f2f3f5; font-family: "Sans"; font-size: 12px; }
QLabel { background: transparent; }
QFrame#sidebar { background: #111113; border-right: 1px solid #29292b; }
QFrame#panel { background: #0e0e10; border: 1px solid #424244; border-radius: 11px; }
QFrame#strip { background: transparent; border: 0; }
QLabel#eyebrow { color: #b6b8be; font-size: 11px; font-weight: 700; }
QLabel#section { color: #f4f4f5; font-size: 13px; font-weight: 700; }
QLabel#value { color: #f5f5f6; font-size: 18px; font-weight: 700; }
QLabel#muted { color: #858890; }
QPushButton { background: #282a2f; color: #f3f4f6; border: 1px solid #53565d;
              border-radius: 5px; padding: 8px 13px; }
QPushButton:hover { background: #363940; }
QPushButton:pressed { background: #494d55; }
QPushButton#nav { background: transparent; border: 0; border-radius: 0;
                  text-align: left; padding: 13px 18px; font-weight: 600; }
QPushButton#nav:hover { background: #26282c; }
QPushButton#nav[active="true"] { background: #28282a; border-left: 3px solid #3587ff; }
QPushButton#danger { border-color: #b95a5e; color: #ffb1b3; }
QCheckBox { color: #d5d7dc; spacing: 5px; background: transparent; }
QCheckBox::indicator { width: 17px; height: 17px; }
QCheckBox::indicator:unchecked { background: #1d1f24; border: 1px solid #74777e; border-radius: 3px; }
QCheckBox::indicator:checked { background: #478fff; border: 1px solid #75aaff; border-radius: 3px; }
QComboBox { background: #202227; border: 1px solid #595c64; padding: 7px 10px; border-radius: 5px; }
QComboBox QAbstractItemView { background: #202227; color: white; selection-background-color: #386db8; }
QSlider { background: transparent; }
QSlider::groove:vertical { background: #34363d; width: 5px; border-radius: 2px; }
QSlider::sub-page:vertical { background: #34363d; border-radius: 2px; }
QSlider::add-page:vertical { background: #e6e8ec; border-radius: 2px; }
QSlider::handle:vertical { background: #ffffff; height: 13px; margin: 0 -7px; border-radius: 7px; }
QSlider::groove:horizontal { background: #373940; height: 5px; border-radius: 2px; }
QSlider::sub-page:horizontal { background: #e6e8ec; border-radius: 2px; }
QSlider::handle:horizontal { background: #ffffff; width: 15px; margin: -6px 0; border-radius: 7px; }
QScrollArea { border: 0; }
QScrollBar:vertical { background: #121316; width: 9px; }
QScrollBar::handle:vertical { background: #45474d; border-radius: 4px; }
"""


def label(text: str, kind: str | None = None) -> QLabel:
    result = QLabel(text)
    if kind:
        result.setObjectName(kind)
    return result


def panel(title: str) -> tuple[QFrame, QVBoxLayout]:
    box = QFrame()
    box.setObjectName("panel")
    layout = QVBoxLayout(box)
    layout.setContentsMargins(16, 13, 16, 15)
    layout.setSpacing(0)
    if title:
        layout.addWidget(label(title, "section"))
    return box, layout


def vertical_slider() -> QSlider:
    slider = FaderSlider()
    slider.setRange(0, 127)
    slider.setValue(0)
    slider.setMinimumHeight(130)
    return slider


class FaderSlider(QSlider):
    """Draw the narrow rail and round white fader cap in the vendor app."""

    def __init__(self, parent=None):
        super().__init__(Qt.Orientation.Vertical, parent)
        self.setFixedWidth(18)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        center = self.width() / 2
        top, bottom = 7, self.height() - 7
        position = bottom - (self.value() / max(1, self.maximum())) * (bottom - top)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#343436"))
        painter.drawRoundedRect(round(center - 2), top, 4, bottom - top, 2, 2)
        painter.setBrush(QColor("#f7f7f7"))
        painter.drawRoundedRect(round(center - 2), round(position), 4,
                                max(0, round(bottom - position)), 2, 2)
        unity = bottom - (100 / max(1, self.maximum())) * (bottom - top)
        painter.setBrush(QColor("#aaaaaa"))
        painter.drawRect(0, round(unity), self.width(), 1)
        painter.setBrush(QColor("#f7f7f7"))
        painter.drawEllipse(round(center - 6), round(position - 6), 12, 12)


class LevelMeter(QWidget):
    """Roland-style dotted peak meter beside a fader."""

    def __init__(self, dots: int, parent=None):
        super().__init__(parent)
        self.dots = dots
        self.level = 0
        self.setFixedWidth(9)
        self.setMinimumHeight(72)
        self.setToolTip("Live audio level from the BRIDGE CAST ONE")

    def set_level(self, value: int):
        value = max(0, min(127, value))
        if value != self.level:
            self.level = value
            self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        lit = round(self.level * self.dots / 127)
        step = self.height() / self.dots
        for index in range(self.dots):
            y = self.height() - (index + .5) * step
            if index < lit:
                color = QColor("#f5f5f5")
            elif index >= self.dots - 5:
                color = QColor("#363307")
            else:
                color = QColor("#333438")
            painter.setBrush(color)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(2, round(y - 2), 4, 4)


class BridgeCastApp(QMainWindow):
    def __init__(self, port: str | None, *, connect_device: bool = True):
        super().__init__()
        self.port = port
        self.device: BridgeCastOne | None = None
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.pending = None
        self.pending_done = None
        self.refreshing = False
        self.last_snapshot = None
        self.last_mic_snapshot = None
        self.faders: dict[int, list[tuple[QSlider, QLabel]]] = {}
        self.mutes: dict[int, list[QCheckBox]] = {}
        self.output_levels: dict[str, list[QLabel]] = {}
        self.output_sliders: dict[str, list[QSlider]] = {}
        self.input_meters: dict[int, list[LevelMeter]] = {}
        self.output_meters: dict[str, LevelMeter] = {}
        self.featured_values: dict[int, QLabel] = {}
        self.meter_pending = None
        self.line_out_sliders: list[QSlider] = []
        self.mic_controls: dict[int, tuple[QWidget, QLabel | None]] = {}
        self.mic_gain_controls: dict[int, tuple[QSlider, QLabel]] = {}
        self.nav_buttons: list[QPushButton] = []
        self.setWindowTitle(f"BRIDGE CAST ONE for Linux v{APP_VERSION}")
        self.setMinimumSize(1100, 720)
        self.resize(1346, 740)
        icon = ASSETS / "bridgecast-linux-icon.png"
        if icon.is_file():
            self.setWindowIcon(QIcon(str(icon)))
        self.setStyleSheet(STYLE)
        self._build()
        self.timer = QTimer(self)
        self.timer.setInterval(40)
        self.timer.timeout.connect(self._poll)
        self.meter_timer = QTimer(self)
        self.meter_timer.setInterval(40)
        self.meter_timer.timeout.connect(self._refresh_meters)
        if connect_device:
            self._submit(self._connect, "Connecting", self._connected)

    def _build(self):
        root = QWidget()
        self.setCentralWidget(root)
        shell = QVBoxLayout(root)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)
        menu = QMenuBar()
        menu.setNativeMenuBar(False)
        menu.setFixedHeight(21)
        menu.setStyleSheet(
            "QMenuBar { background: #f5f5f5; color: #171717; font-size: 11px; }"
            "QMenuBar::item { padding: 2px 8px; background: transparent; }"
            "QMenuBar::item:selected { background: #d5d5d5; }"
            "QMenu { background: #f5f5f5; color: #171717; }"
            "QMenu::item:selected { background: #c8dcff; }")
        zoom = menu.addMenu("Zoom")
        zoom.addAction("100%", lambda: self.resize(1346, 740))
        device_menu = menu.addMenu("Device")
        device_menu.addAction("Refresh", self.refresh)
        device_menu.addAction("Reconnect", self.reconnect)
        device_menu.addSeparator()
        device_menu.addAction("Stop mic monitoring", self.stop_mic_monitoring)
        driver = menu.addMenu("Driver")
        driver.setEnabled(False)
        help_menu = menu.addMenu("Help")
        help_menu.addAction("About", lambda: QMessageBox.information(
            self, "BRIDGE CAST ONE for Linux",
            f"Version {APP_VERSION}\nUnofficial Linux controller for BRIDGE CAST ONE"))
        self.status = QLabel("Connecting…")
        self.status.setStyleSheet("color: #323232; background: #f5f5f5; font-size: 10px; padding-right: 10px;")
        menu.setCornerWidget(self.status, Qt.Corner.TopRightCorner)
        shell.addWidget(menu)

        body = QWidget()
        overall = QHBoxLayout(body)
        overall.setContentsMargins(0, 0, 0, 0)
        overall.setSpacing(0)
        shell.addWidget(body, 1)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(182)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 16)
        sidebar_layout.setSpacing(1)
        brand = QLabel("BRIDGE CAST ONE")
        brand.setFixedHeight(54)
        brand.setStyleSheet("background: #000; color: white; font-size: 15px; padding-left: 18px;")
        sidebar_layout.addWidget(brand)
        sidebar_layout.addSpacing(22)

        self.pages = QStackedWidget()
        for name, builder in (
            ("HOME", self._build_home),
            ("MIC SETUP", self._build_mic_setup),
            ("MIC CLEANUP", self._build_mic_cleanup),
            ("OUTPUT", self._build_output),
        ):
            button = QPushButton(name)
            button.setObjectName("nav")
            button.setFixedHeight(50)
            self._set_nav_icon(button, name)
            index = len(self.nav_buttons)
            button.clicked.connect(lambda _checked=False, i=index: self._switch_page(i))
            sidebar_layout.addWidget(button)
            self.nav_buttons.append(button)
            self.pages.addWidget(builder())
            if name == "MIC CLEANUP":
                self._unmapped_nav(sidebar_layout, "VOICE TRANSFORMER")
                self._unmapped_nav(sidebar_layout, "GAME (USB)")
                self._unmapped_nav(sidebar_layout, "CHAT")
            if name == "OUTPUT":
                self._unmapped_nav(sidebar_layout, "PROFILE")
                self._unmapped_nav(sidebar_layout, "SYSTEM")
                self._unmapped_nav(sidebar_layout, "BGM CAST")
        sidebar_layout.addStretch()
        image = ASSETS / "bridge-cast-one.png"
        if image.is_file():
            art = QLabel()
            art.setPixmap(QPixmap(str(image)).scaled(
                144, 144, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation))
            art.setAlignment(Qt.AlignmentFlag.AlignCenter)
            sidebar_layout.addWidget(art)
        overall.addWidget(sidebar)

        main = QWidget()
        main_layout = QVBoxLayout(main)
        main_layout.setContentsMargins(55, 53, 41, 14)
        main_layout.setSpacing(5)
        main_layout.addWidget(self.pages, 1)
        overall.addWidget(main, 1)
        self._switch_page(0)

    @staticmethod
    def _unmapped_nav(layout: QVBoxLayout, title: str):
        button = QPushButton(title)
        button.setObjectName("nav")
        button.setFixedHeight(56 if title == "VOICE TRANSFORMER" else 50)
        if title == "VOICE TRANSFORMER":
            button.setText("VOICE\nTRANSFORMER")
        BridgeCastApp._set_nav_icon(button, title)
        button.setToolTip("This page has not been mapped on BRIDGE CAST ONE yet")
        button.clicked.connect(lambda: QMessageBox.information(
            button, title, "This page is not available in the Linux controller yet."))
        layout.addWidget(button)

    @staticmethod
    def _set_nav_icon(button: QPushButton, title: str):
        path = ASSETS / f"nav-{NAV_ICONS[title]}.png"
        if path.is_file():
            button.setIcon(QIcon(str(path)))
            button.setIconSize(QSize(26, 26))

    def _scroll_page(self) -> tuple[QScrollArea, QVBoxLayout]:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(2, 2, 8, 2)
        layout.setSpacing(6)
        scroll.setWidget(body)
        return scroll, layout

    def _switch_page(self, index: int):
        self.pages.setCurrentIndex(index)
        for i, button in enumerate(self.nav_buttons):
            button.setProperty("active", i == index)
            button.style().unpolish(button)
            button.style().polish(button)

    def _register_fader(self, address: int, slider: QSlider, value: QLabel):
        self.faders.setdefault(address, []).append((slider, value))
        slider.valueChanged.connect(lambda number, view=value: view.setText(str(number)))
        slider.sliderReleased.connect(
            lambda a=address, control=slider: self._set_level(a, control.value()))

    def _register_mute(self, address: int, control: QCheckBox):
        self.mutes.setdefault(address, []).append(control)
        control.clicked.connect(
            lambda checked, a=address, c=control: self._set_mute(a, checked, c))

    def _build_home(self) -> QWidget:
        scroll, layout = self._scroll_page()
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        upper = QHBoxLayout()
        upper.setSpacing(8)
        dial, dial_layout = panel("")
        dial.setFixedWidth(192)
        dial.setMinimumHeight(369)
        dial_layout.setSpacing(6)
        dial_layout.setContentsMargins(16, 11, 16, 37)
        ring = QLabel()
        ring.setFixedSize(154, 154)
        dial_asset = ASSETS / "bridge-cast-one-dial.png"
        if dial_asset.is_file():
            ring.setPixmap(QPixmap(str(dial_asset)))
        else:
            ring.setStyleSheet(
                "background: #050506; border: 4px solid #35dc54; border-radius: 77px;")
        dial_layout.addWidget(ring, alignment=Qt.AlignmentFlag.AlignHCenter)
        dial_layout.addStretch()
        dial_mode = label("DIAL MODE", "section")
        dial_mode.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dial_layout.addWidget(dial_mode)
        for title in ("SEPARATE", "BALANCE 1", "BALANCE 2"):
            option = QPushButton(title)
            option.setFixedSize(114, 20)
            option.setStyleSheet(
                "QPushButton { padding: 1px 5px; color: #aeb0b5; "
                "background: #26282c; border: 1px solid #41434a; border-radius: 4px; }")
            option.setEnabled(False)
            option.setToolTip("Dial mode commands have not been verified on this unit")
            dial_layout.addWidget(option, alignment=Qt.AlignmentFlag.AlignHCenter)
            if title != "BALANCE 2":
                dial_layout.addSpacing(4)
        upper.addWidget(dial)
        inputs, inputs_layout = panel("INPUT")
        inputs.setMinimumHeight(369)
        main_strips = QHBoxLayout()
        main_strips.setSpacing(4)
        for index in (0, 2, 3):
            main_strips.addWidget(self._channel_strip(index, featured=True), 1)
        inputs_layout.addLayout(main_strips)
        upper.addWidget(inputs, 1)
        layout.addLayout(upper)

        lower = QHBoxLayout()
        lower.setSpacing(8)
        secondary, secondary_layout = panel("MORE INPUTS")
        secondary.setMinimumHeight(273)
        secondary_strips = QHBoxLayout()
        secondary_strips.setSpacing(4)
        for index in (1, 4, 5, 6):
            secondary_strips.addWidget(self._channel_strip(index), 1)
        secondary_layout.addLayout(secondary_strips)
        lower.addWidget(secondary, 13)
        outputs, outputs_layout = panel("OUTPUT")
        outputs.setMinimumHeight(273)
        output_row = QHBoxLayout()
        output_row.setSpacing(3)
        for name in ("Personal", "Stream", "Line Out", "Phones"):
            output_row.addWidget(self._output_strip(name), 1)
        outputs_layout.addLayout(output_row)
        lower.addWidget(outputs, 8)
        layout.addLayout(lower)
        self.summary = label("Reading device mixer…", "eyebrow")
        layout.addStretch()
        return scroll

    def _channel_strip(self, index: int, *, featured: bool = False) -> QFrame:
        name = CHANNELS[index]
        display_name = "GAME(SPEAKER)" if index == 4 else name.upper()
        strip = QFrame()
        strip.setObjectName("strip")
        if featured and index in (0, 2):
            strip.setStyleSheet("QFrame#strip { border-right: 1px solid #43444a; }")
        strip_layout = QVBoxLayout(strip)
        strip_layout.setContentsMargins(5, 0, 5, 8)
        strip_layout.setSpacing(20 if featured else 5)
        name_row = QHBoxLayout()
        name_row.setSpacing(0)
        name_label = label(display_name, "section")
        name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_label.setStyleSheet("color: #f4f4f4;")
        if featured:
            name_row.addSpacing(7)
            for marker in (("♟", "◈", "◉") if index == 0 else ("●", "◉")):
                icon = label(marker, "section")
                icon.setFixedWidth(20)
                icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
                name_row.addWidget(icon)
                name_row.addSpacing(15)
            name_row.addStretch()
            name_label.setFixedSize(112, 20)
            border = "#2382ff" if index == 0 else "#29292d"
            name_label.setStyleSheet(
                f"color: #f4f4f4; border: 1px solid {border}; font-weight: 700;")
            name_row.addWidget(name_label)
            name_row.addSpacing(7)
            current = label("—", "section")
            current.setFixedWidth(27)
            current.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            current.setToolTip("Stream Mix fader level; the vendor header uses a separate scale")
            name_row.addWidget(current)
            self.featured_values[index] = current
        else:
            name_row.addStretch()
            name_row.addWidget(name_label)
            name_row.addStretch()
        strip_layout.addLayout(name_row)
        body = QHBoxLayout()
        body.setSpacing(0 if featured else 4)
        sliders = QHBoxLayout()
        sliders.setSpacing(3)
        for title, addresses, mutes in (
            ("PERSONAL", PERSONAL_FADERS, PERSONAL_MUTES),
            ("STREAM", STREAM_FADERS, STREAM_MUTES),
        ):
            column = QVBoxLayout()
            if not featured:
                caption = label("●" if title == "PERSONAL" else "◉", "section")
                caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
                caption.setToolTip(title.title() + " Mix")
                column.addWidget(caption)
                column.addSpacing(16)
            slider = vertical_slider()
            if featured:
                slider.setFixedHeight(240)
            else:
                slider.setFixedHeight(130)
            track = QHBoxLayout()
            track.setSpacing(5)
            track.addWidget(slider)
            meter = LevelMeter(24 if featured else 14)
            meter.setFixedHeight(240 if featured else 130)
            track.addWidget(meter)
            column.addLayout(track, 1)
            self.input_meters.setdefault(index, []).append(meter)
            value = label("—", "value")
            value.hide()
            column.addWidget(value)
            self._register_fader(addresses[index], slider, value)
            slider.valueChanged.connect(
                lambda number, control=slider, channel=name, mix=title:
                control.setToolTip(f"{channel} {mix.title()} Mix: {number}/127"))
            if index < len(mutes):
                toggle = QCheckBox("IN")
                toggle.setToolTip(f"Include {name} in {title.lower()} mix")
                self._register_mute(mutes[index], toggle)
                column.addWidget(toggle, alignment=Qt.AlignmentFlag.AlignHCenter)
            else:
                column.addWidget(label(" ", "muted"))
            sliders.addLayout(column)
        if featured:
            sliders.setContentsMargins(0, 0, 0, 0)
            sliders.setSpacing(0)
            slider_box = QWidget()
            slider_box.setFixedWidth(70)
            slider_box.setStyleSheet("background: transparent;")
            slider_box.setLayout(sliders)
            if index != 0:
                body.addSpacing(18)
            body.addWidget(slider_box)
            body.addSpacing(38 if index == 0 else 20)
        else:
            body.addLayout(sliders, 1)
        if featured:
            led = QFrame()
            led.setFixedSize(52, 52)
            led.setStyleSheet(
                f"background: #090a0c; border: 5px solid {FEATURED_COLORS[index]}; border-radius: 26px;")
            led.setToolTip("Hardware LED graphic; color setting is not mapped")
            led_column = QVBoxLayout()
            led_column.setSpacing(0)
            led_column.addSpacing(14)
            led_column.addWidget(led, alignment=Qt.AlignmentFlag.AlignHCenter)
            led_column.addSpacing(18)
            source = QPushButton(FEATURED_SOURCES[index] + "  ▾")
            source.setEnabled(False)
            source.setToolTip("Source assignment is shown from the reference image; device mapping is pending")
            source.setFixedSize(112, 23)
            source.setStyleSheet(
                "QPushButton { background: #0c0c0e; border: 1px solid #303034; "
                "border-radius: 0; padding: 1px 3px; color: #f0f0f0; font-weight: 700; }")
            led_column.addWidget(source)
            led_column.addSpacing(52)
            mute = QPushButton("MUTE PERSONAL ▾" if index == 0 else "MUTE ALL  ▾")
            mute.setEnabled(False)
            mute.setToolTip("Vendor mute menu is not mapped; use the working IN toggles below the faders")
            mute.setFixedSize(112, 23)
            mute.setStyleSheet(
                "QPushButton { background: #0c0c0e; border: 1px solid #303034; "
                "border-radius: 0; padding: 1px 3px; color: #f0f0f0; font-weight: 700; }")
            led_column.addWidget(mute)
            led_column.addStretch()
            body.addLayout(led_column)
            body.addSpacing(18)
            spectrum = QFrame()
            spectrum.setFixedSize(4, 240)
            spectrum.setStyleSheet(
                "background: qlineargradient(x1:0, y1:0, x2:0, y2:1, "
                "stop:0 #ff004b, stop:0.17 #9f00eb, stop:0.37 #008eff, "
                "stop:0.56 #00ee97, stop:0.75 #ffeb00, stop:1 #ff233f);")
            body.addWidget(spectrum, alignment=Qt.AlignmentFlag.AlignTop)
            body.addStretch()
        strip_layout.addLayout(body, 1)
        return strip

    def _output_strip(self, name: str) -> QFrame:
        card = QFrame()
        card.setObjectName("strip")
        column = QVBoxLayout(card)
        column.setContentsMargins(3, 0, 3, 8)
        column.setSpacing(4)
        heading = label("SUB MIX" if name == "Personal" else name.upper(), "eyebrow")
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        column.addWidget(heading)
        if name == "Personal":
            column.addWidget(label("♧", "section"), alignment=Qt.AlignmentFlag.AlignHCenter)
            column.addSpacing(17)
            slider = vertical_slider()
            slider.setFixedHeight(130)
            slider.setEnabled(False)
            slider.setToolTip("SUB MIX level is read from the device; write command is not verified")
            meter = LevelMeter(12)
            meter.setFixedHeight(130)
            track = QHBoxLayout()
            track.setSpacing(5)
            track.addWidget(slider)
            track.addWidget(meter)
            column.addLayout(track, 1)
            self.output_sliders.setdefault(name, []).append(slider)
            self.output_meters[name] = meter
            column.addWidget(label("∞", "section"), alignment=Qt.AlignmentFlag.AlignHCenter)
            return card
        slider = vertical_slider()
        column.addWidget(label("◉" if name != "Line Out" else "◖))", "section"),
                         alignment=Qt.AlignmentFlag.AlignHCenter)
        column.addSpacing(17)
        slider.setFixedHeight(130)
        track = QHBoxLayout()
        track.setSpacing(5)
        track.addWidget(slider)
        meter = LevelMeter(12)
        meter.setFixedHeight(130)
        track.addWidget(meter)
        column.addLayout(track, 1)
        self.output_meters[name] = meter
        self.output_sliders.setdefault(name, []).append(slider)
        if name == "Line Out":
            self.line_out_sliders.append(slider)
            slider.sliderReleased.connect(
                lambda control=slider: self._set_level(0x58, control.value()))
        else:
            slider.setEnabled(False)
            slider.setToolTip(f"{name} level is read-only until its write command is verified")
        value = label("—", "value")
        value.hide()
        column.addWidget(value)
        self.output_levels.setdefault(name, []).append(value)
        toggle = QCheckBox("ON")
        self._register_mute(OUTPUT_MUTES[name], toggle)
        column.addWidget(toggle, alignment=Qt.AlignmentFlag.AlignHCenter)
        return card

    def _build_mic_setup(self) -> QWidget:
        scroll, layout = self._scroll_page()
        setup, box = panel("MIC SETUP")
        box.addWidget(label("Input source and phantom power are read from the device.", "muted"))
        details = QHBoxLayout()
        self.mic_source = label("SOURCE  —", "value")
        self.phantom = label("48V  —", "value")
        details.addWidget(self.mic_source)
        details.addWidget(self.phantom)
        details.addStretch()
        box.addLayout(details)
        for title, address in (("XLR GAIN", 0x22), ("HEADSET GAIN", 0x24)):
            row = QHBoxLayout()
            row.addWidget(label(title, "eyebrow"))
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(0, 25)
            slider.sliderReleased.connect(
                lambda a=address, control=slider: self._set_mic_gain(a, control.value()))
            row.addWidget(slider, 1)
            value = label("—", "value")
            row.addWidget(value)
            self.mic_gain_controls[address] = (slider, value)
            box.addLayout(row)
        box.addWidget(label(
            "Source selection and phantom power are shown for diagnosis; their write commands are not verified.",
            "muted"))
        layout.addWidget(setup)
        layout.addStretch()
        return scroll

    def _mic_toggle(self, parent: QVBoxLayout, title: str, address: int):
        toggle = QCheckBox(title)
        toggle.clicked.connect(lambda checked, a=address: self._set_mic_fx(a, int(checked)))
        parent.addWidget(toggle)
        self.mic_controls[address] = (toggle, None)

    def _mic_slider(self, parent: QVBoxLayout, title: str, address: int):
        row = QHBoxLayout()
        row.addWidget(label(title, "eyebrow"))
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(0, MIC_FX_LIMITS[address])
        slider.sliderReleased.connect(
            lambda a=address, control=slider: self._set_mic_fx(a, control.value()))
        row.addWidget(slider, 1)
        value = label("—", "value")
        value.setMinimumWidth(95)
        row.addWidget(value)
        parent.addLayout(row)
        self.mic_controls[address] = (slider, value)

    def _build_mic_cleanup(self) -> QWidget:
        scroll, layout = self._scroll_page()
        grid = QGridLayout()
        grid.setSpacing(12)
        for title, row, col, enabled, controls in (
            ("LOW CUT", 0, 0, 0x00, (("Frequency", 0x02),)),
            ("NOISE SUPPRESSION", 0, 1, 0x10, (("Threshold", 0x12),)),
            ("DE-ESSER", 1, 0, 0x20, (("Depth", 0x22),)),
            ("MANUAL EQ", 1, 1, 0x30, ()),
            ("COMPRESSOR", 2, 0, 0x70, (
                ("Attack", 0x72), ("Release", 0x74), ("Threshold", 0x76),
                ("Ratio", 0x78), ("Post Gain", 0x7A))),
        ):
            box, contents = panel(title)
            self._mic_toggle(contents, "ENABLED", enabled)
            for control_title, address in controls:
                self._mic_slider(contents, control_title, address)
            if title == "MANUAL EQ":
                contents.addWidget(label("Band editing is not mapped yet.", "muted"))
            grid.addWidget(box, row, col)
        layout.addLayout(grid)
        refresh = QPushButton("Refresh mic settings")
        refresh.clicked.connect(self.refresh_mic)
        layout.addWidget(refresh, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addStretch()
        return scroll

    def _build_output(self) -> QWidget:
        scroll, layout = self._scroll_page()
        box, contents = panel("OUTPUT")
        contents.addWidget(label("LINE OUT", "eyebrow"))
        row = QHBoxLayout()
        row.addWidget(label("SOURCE", "eyebrow"))
        self.mode = QComboBox()
        self.mode.addItems(("Stream Mix", "Phones Sync"))
        self.mode.activated.connect(self._set_mode)
        row.addWidget(self.mode)
        row.addStretch()
        contents.addLayout(row)
        level_row = QHBoxLayout()
        level_row.addWidget(label("LEVEL", "eyebrow"))
        self.line_out_slider = QSlider(Qt.Orientation.Horizontal)
        self.line_out_slider.setRange(0, 127)
        self.line_out_slider.sliderReleased.connect(
            lambda: self._set_level(0x58, self.line_out_slider.value()))
        self.line_out_sliders.append(self.line_out_slider)
        level_row.addWidget(self.line_out_slider, 1)
        self.line_out_value = label("—", "value")
        level_row.addWidget(self.line_out_value)
        contents.addLayout(level_row)
        contents.addWidget(label(
            "Stream Mix is the current working route. Phones Sync follows the headphone mix.", "muted"))
        contents.addWidget(label(
            "The MIC-only LINE OUT route is hidden because it can cause loud speaker feedback.", "muted"))
        layout.addWidget(box)
        state, state_layout = panel("OUTPUT STATE")
        for name in OUTPUT_LEVELS:
            row = QHBoxLayout()
            row.addWidget(label(name.upper(), "eyebrow"))
            value = label("—", "value")
            self.output_levels.setdefault(name, []).append(value)
            row.addWidget(value)
            row.addStretch()
            toggle = QCheckBox("ENABLED")
            self._register_mute(OUTPUT_MUTES[name], toggle)
            row.addWidget(toggle)
            state_layout.addLayout(row)
        state_layout.addWidget(label(
            "STREAM and PHONES levels are readouts; their write behavior has not been verified.", "muted"))
        layout.addWidget(state)
        layout.addStretch()
        return scroll

    def _submit(self, operation, description: str, done=None):
        if self.pending is not None:
            self.status.setText("Please wait for the current device operation")
            return
        self.status.setText(description + "…")
        self.pending_done = done
        self.pending = self.executor.submit(operation)
        self.timer.start()

    def _poll(self):
        if not self.pending or not self.pending.done():
            return
        self.timer.stop()
        future, done = self.pending, self.pending_done
        self.pending = None
        self.pending_done = None
        try:
            result = future.result()
        except Exception as error:
            if self.last_snapshot is not None:
                self._display(self.last_snapshot)
            if self.last_mic_snapshot is not None:
                self._display_mic(self.last_mic_snapshot)
            self.status.setText(f"Device error: {error}")
            return
        if done:
            done(result)
        if self.pending is None:
            self.status.setText(f"Connected on {self.device.port}" if self.device else "Disconnected")

    def _connect(self):
        if self.device:
            self.device.close()
        self.device = BridgeCastOne(self.port)
        return self.device.snapshot()

    def _connected(self, snapshot):
        self._display(snapshot)
        self.meter_timer.start()
        QTimer.singleShot(0, self.refresh_mic)

    def _refresh_meters(self):
        if self.meter_pending is not None:
            if not self.meter_pending.done():
                return
            future = self.meter_pending
            self.meter_pending = None
            try:
                self._display_meters(future.result())
            except Exception:
                # A competing MIDI client may consume a reply. The next tick
                # will retry without interrupting the mixer controls.
                pass
        if self.device is not None and self.pending is None:
            self.meter_pending = self.executor.submit(self.device.meter_snapshot)

    @staticmethod
    def _stereo_peak(data: bytes, offset: int) -> int:
        return max(data[offset], data[offset + 2]) if offset + 2 < len(data) else 0

    def _display_meters(self, data: bytes):
        # Each stereo peak is two 7-bit bytes per side. The high bytes map
        # directly to the vendor's 0..127 meter scale.
        for index, meters in self.input_meters.items():
            for mix_index, meter in enumerate(meters):
                offset = 0x1f + index * 4 + mix_index * 0x20
                meter.set_level(self._stereo_peak(data, offset))
        for name, offset in (("Personal", 0x5f), ("Stream", 0x61),
                             ("Line Out", 0x65), ("Phones", 0x6d)):
            self.output_meters[name].set_level(self._stereo_peak(data, offset))

    def reconnect(self):
        self._submit(self._connect, "Reconnecting", self._connected)

    def refresh(self):
        if self.device is None:
            self.reconnect()
        else:
            self._submit(self.device.snapshot, "Reading mixer", self._display)

    def _display(self, snapshot):
        self.last_snapshot = snapshot
        bank, route = snapshot
        self.refreshing = True
        try:
            for address, controls in self.faders.items():
                for slider, value in controls:
                    slider.setValue(bank[address])
                    value.setText(str(bank[address]))
            for index, value in self.featured_values.items():
                value.setText(str(bank[STREAM_FADERS[index]]))
            for address, controls in self.mutes.items():
                for control in controls:
                    control.setChecked(bool(bank[address]))
            for name, address in OUTPUT_LEVELS.items():
                for value in self.output_levels.get(name, []):
                    value.setText(f"{bank[address]} / 127")
                for slider in self.output_sliders.get(name, []):
                    slider.setValue(bank[address])
            for slider in self.output_sliders.get("Personal", []):
                slider.setValue(bank[0x52])
            for slider in self.line_out_sliders:
                slider.setValue(bank[0x58])
            self.line_out_value.setText(f"{bank[0x58]} / 127")
            mode = LINE_OUT_MODES.get(route, f"Unknown ({route})")
            self.mode.setCurrentText(mode)
            music = CHANNELS.index("Music")
            music_state = "in mix" if bank[STREAM_MUTES[music]] else "muted"
            mic_state = "in mix" if bank[STREAM_MUTES[0]] else "off"
            self.summary.setText(
                f"MUSIC {bank[STREAM_FADERS[music]]}/127 · {music_state}     "
                f"LINE OUT {bank[0x58]}/127 · {mode}     MIC MONITOR {mic_state}")
        finally:
            self.refreshing = False

    def refresh_mic(self):
        if self.device is None:
            return
        self._submit(
            lambda: (self.device.mic_fx_snapshot(), self.device.mic_input_snapshot()),
            "Reading mic settings", self._display_mic)

    def _display_mic(self, snapshot):
        self.last_mic_snapshot = snapshot
        values, input_values = snapshot
        self.refreshing = True
        try:
            for address, (control, value) in self.mic_controls.items():
                if value is None:
                    control.setChecked(bool(values[address]))
                else:
                    control.setValue(values[address])
                    value.setText(MIC_FORMAT[address](values[address]))
            source = {0: "XLR", 1: "HEADSET"}.get(
                input_values[0x20], f"UNKNOWN ({input_values[0x20]})")
            self.mic_source.setText(f"SOURCE  {source}")
            self.phantom.setText(f"48V  {'ON' if input_values[0x26] else 'OFF'}")
            for address, (slider, value) in self.mic_gain_controls.items():
                raw = input_values[address]
                slider.setValue(raw)
                db = raw * (3 if address == 0x22 else 1.52)
                value.setText(f"{db:.0f} dB")
        finally:
            self.refreshing = False

    def _write_and_read(self, address: int, value: int):
        self.device.set_fader(address, value)
        time.sleep(0.05)
        snapshot = self.device.snapshot()
        if snapshot[0][address] != value:
            raise RuntimeError(
                f"Device did not accept setting {address:02x}; read back {snapshot[0][address]}")
        return snapshot

    def _set_level(self, address: int, value: int):
        if self.refreshing or self.device is None:
            return
        self._submit(lambda: self._write_and_read(address, value), "Setting level", self._display)

    def _set_mute(self, address: int, enabled: bool, control: QCheckBox):
        if self.refreshing or self.device is None:
            return
        if address in (STREAM_MUTES[0], PERSONAL_MUTES[0]) and enabled:
            answer = QMessageBox.question(
                self, "Enable mic in mix?",
                "This can play your microphone through speakers and cause feedback. Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                control.setChecked(False)
                return
        self._submit(
            lambda: self._write_and_read(address, int(enabled)),
            "Changing channel state", self._display)

    def _set_mode(self, _index: int):
        if self.refreshing or self.device is None:
            return
        modes = {name: value for value, name in LINE_OUT_MODES.items() if value in (1, 2)}
        value = modes.get(self.mode.currentText())
        if value is None:
            return
        def operation():
            self.device.set_line_out_mode(value)
            time.sleep(0.05)
            snapshot = self.device.snapshot()
            if snapshot[1] != value:
                raise RuntimeError(f"Device did not accept LINE OUT mode; read back {snapshot[1]}")
            return snapshot
        self._submit(operation, "Changing LINE OUT source", self._display)

    def _set_mic_fx(self, address: int, value: int):
        if self.refreshing or self.device is None:
            return
        def operation():
            self.device.set_mic_fx(address, value)
            time.sleep(0.05)
            values = self.device.mic_fx_snapshot()
            if values[address] != value:
                raise RuntimeError(f"Device did not accept mic setting {address:02x}; read back {values[address]}")
            return values, self.device.mic_input_snapshot()
        self._submit(operation, "Setting mic processing", self._display_mic)

    def _set_mic_gain(self, address: int, value: int):
        if self.refreshing or self.device is None:
            return
        def operation():
            self.device.set_mic_gain(address, value)
            time.sleep(0.05)
            inputs = self.device.mic_input_snapshot()
            if inputs[address] != value:
                raise RuntimeError(f"Device did not accept mic gain {address:02x}; read back {inputs[address]}")
            return self.device.mic_fx_snapshot(), inputs
        self._submit(operation, "Setting mic gain", self._display_mic)

    def stop_mic_monitoring(self):
        if self.device is None:
            return
        def operation():
            self.device.set_fader(STREAM_MUTES[0], 0)
            self.device.set_fader(PERSONAL_MUTES[0], 0)
            time.sleep(0.05)
            snapshot = self.device.snapshot()
            if snapshot[0][STREAM_MUTES[0]] or snapshot[0][PERSONAL_MUTES[0]]:
                raise RuntimeError("Mic monitoring did not turn off on both device mixes")
            return snapshot
        self._submit(operation, "Stopping mic monitoring", self._display)

    def closeEvent(self, event):
        self.timer.stop()
        self.meter_timer.stop()
        self.executor.shutdown(wait=True, cancel_futures=True)
        if self.device:
            self.device.close()
        super().closeEvent(event)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", help="APP MIDI port; auto-detected by default")
    parser.add_argument("--version", action="version", version=f"BRIDGE CAST ONE for Linux {APP_VERSION}")
    args = parser.parse_args()
    application = QApplication(sys.argv[:1])
    window = BridgeCastApp(args.port)
    window.show()
    sys.exit(application.exec())


if __name__ == "__main__":
    main()
