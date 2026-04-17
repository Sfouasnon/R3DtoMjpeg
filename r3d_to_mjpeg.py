#!/usr/bin/env python3
"""
R3D → MJPEG MOV Transcoder  |  Vicon VideoCalibrator Prep
==========================================================
Transcodes RED R3D files to MJPEG .MOV files ready for
Vicon's VideoCalibrator.exe.

Output spec (per Vicon docs):
  • Container:  QuickTime .mov
  • Codec:      MJPEG  (Motion JPEG)
  • Quality:    High (low compression)
  • Audio:      Stripped  (-an)
  • Timecode:   Stripped  (-write_tmcd 0)
  • Sync:       All clips must share matching frame indices

Transcoder backends (in order of preference):
  1. REDline  —  if installed, gives full RAW colour pipeline
  2. FFmpeg   —  universal fallback, reads R3D via libavcodec

Requirements:
    pip install PySide6

FFmpeg must be on PATH or specified manually.
REDline (REDline.exe) must be on PATH or in its default install location.

Usage:
    python3 r3d_to_mjpeg.py
"""

import sys
import os
import re
import subprocess
import shutil
from pathlib import Path
from typing import List, Optional

try:
    from PySide6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QLabel, QPushButton, QLineEdit, QTextEdit, QFileDialog,
        QFrame, QGroupBox, QSpinBox, QDoubleSpinBox, QCheckBox,
        QComboBox, QProgressBar, QListWidget, QListWidgetItem,
        QAbstractItemView, QSizePolicy,
    )
    from PySide6.QtCore import Qt, QThread, Signal, QMimeData
    from PySide6.QtGui import QColor, QPalette, QDragEnterEvent, QDropEvent
except ImportError:
    print("PySide6 not found.  Install with:  pip install PySide6")
    sys.exit(1)


# ============================================================================
#  CONSTANTS
# ============================================================================

# Default REDline locations on Windows
REDLINE_CANDIDATES = [
    r"C:\Program Files\Red Digital Cinema\REDline\REDline.exe",
    r"C:\Program Files\REDCINE-X PRO\REDline.exe",
    r"C:\Program Files (x86)\Red Digital Cinema\REDline\REDline.exe",
]

DARK_BG  = '#0d1117'
PANEL_BG = '#161b22'
BORDER   = '#30363d'
ACCENT   = '#58a6ff'
ACCENT2  = '#f78166'
TEXT_PRI = '#e6edf3'
TEXT_SEC = '#8b949e'
SUCCESS  = '#3fb950'
ERR      = '#f85149'
WARN     = '#d29922'
LOG_FG   = '#79c0ff'

STYLE = f"""
QMainWindow, QWidget {{
    background: {DARK_BG};
    color: {TEXT_PRI};
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: 12px;
}}
QGroupBox {{
    border: 1px solid {BORDER};
    border-radius: 5px;
    margin-top: 18px;
    padding-top: 8px;
    color: {TEXT_SEC};
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 2px;
    text-transform: uppercase;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
}}
QLineEdit {{
    background: {PANEL_BG};
    border: 1px solid {BORDER};
    border-radius: 3px;
    padding: 6px 9px;
    color: {TEXT_PRI};
}}
QLineEdit:focus {{ border-color: {ACCENT}; }}
QPushButton {{
    background: {PANEL_BG};
    border: 1px solid {BORDER};
    border-radius: 3px;
    padding: 6px 14px;
    color: {TEXT_SEC};
    font-weight: 600;
}}
QPushButton:hover {{ border-color: {ACCENT}; color: {ACCENT}; }}
QPushButton#go_btn {{
    background: #0d2547;
    border: 1px solid {ACCENT};
    color: {ACCENT};
    font-size: 13px;
    font-weight: 700;
    padding: 10px 28px;
    letter-spacing: 2px;
    border-radius: 4px;
}}
QPushButton#go_btn:hover {{ background: #112f5e; }}
QPushButton#go_btn:disabled {{
    background: {PANEL_BG};
    border-color: {BORDER};
    color: #3d444d;
}}
QPushButton#danger_btn {{
    border-color: {ACCENT2};
    color: {ACCENT2};
}}
QPushButton#danger_btn:hover {{
    background: #2d1a1a;
}}
QListWidget {{
    background: {PANEL_BG};
    border: 1px solid {BORDER};
    border-radius: 3px;
    color: {TEXT_PRI};
    padding: 4px;
}}
QListWidget::item:selected {{
    background: #1f3a6b;
    border-radius: 2px;
}}
QTextEdit {{
    background: #010409;
    border: 1px solid {BORDER};
    border-radius: 3px;
    color: {LOG_FG};
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: 11px;
    padding: 6px;
}}
QSpinBox, QDoubleSpinBox, QComboBox {{
    background: {PANEL_BG};
    border: 1px solid {BORDER};
    border-radius: 3px;
    padding: 5px 8px;
    color: {TEXT_PRI};
}}
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
    border: none;
    background: {BORDER};
    width: 16px;
}}
QComboBox::drop-down {{ border: none; }}
QComboBox QAbstractItemView {{
    background: {PANEL_BG};
    border: 1px solid {BORDER};
    color: {TEXT_PRI};
    selection-background-color: #1f3a6b;
}}
QCheckBox {{ color: {TEXT_SEC}; spacing: 8px; }}
QCheckBox::indicator {{
    width: 13px; height: 13px;
    border: 1px solid {BORDER};
    border-radius: 2px;
    background: {PANEL_BG};
}}
QCheckBox::indicator:checked {{
    background: {ACCENT};
    border-color: {ACCENT};
}}
QProgressBar {{
    background: {PANEL_BG};
    border: 1px solid {BORDER};
    border-radius: 2px;
    height: 5px;
    text-align: center;
}}
QProgressBar::chunk {{
    background: {ACCENT};
    border-radius: 2px;
}}
QLabel#title_lbl {{
    font-size: 18px;
    font-weight: 800;
    color: {TEXT_PRI};
    letter-spacing: 1.5px;
}}
QLabel#sub_lbl {{
    font-size: 11px;
    color: {TEXT_SEC};
}}
QLabel#ok_lbl  {{ color: {SUCCESS}; font-weight: 700; }}
QLabel#err_lbl {{ color: {ERR};     font-weight: 700; }}
QLabel#warn_lbl {{ color: {WARN};   font-weight: 700; }}
QFrame#div {{
    background: {BORDER};
    max-height: 1px;
    margin: 2px 0;
}}
"""


# ============================================================================
#  BACKEND DETECTION
# ============================================================================

def find_redline() -> Optional[str]:
    """Return path to REDline.exe or None."""
    # Check PATH first
    found = shutil.which('REDline') or shutil.which('REDline.exe')
    if found:
        return found
    for candidate in REDLINE_CANDIDATES:
        if os.path.isfile(candidate):
            return candidate
    return None


def find_ffmpeg() -> Optional[str]:
    """Return path to ffmpeg or None."""
    return shutil.which('ffmpeg') or shutil.which('ffmpeg.exe')


# ============================================================================
#  TRANSCODE LOGIC
# ============================================================================

def build_ffmpeg_cmd(
    input_path: str,
    output_path: str,
    quality: int = 2,          # MJPEG qscale: 1=best, 31=worst. 2 is near-lossless
    scale_factor: int = 1,     # 1=full, 2=half, 4=quarter
    ffmpeg_exe: str = 'ffmpeg',
) -> List[str]:
    """
    Build FFmpeg command to transcode R3D → MJPEG MOV.

    Per Vicon docs:
      - MJPEG codec, low compression
      - No audio (-an)
      - No timecode (-write_tmcd 0)
    """
    cmd = [ffmpeg_exe, '-y', '-i', input_path]

    vf_filters = []
    if scale_factor > 1:
        vf_filters.append(f'scale=iw/{scale_factor}:ih/{scale_factor}')

    if vf_filters:
        cmd += ['-vf', ','.join(vf_filters)]

    cmd += [
        '-c:v', 'mjpeg',
        '-q:v', str(quality),      # qscale — 1=best, 2=near-lossless, 5=good
        '-an',                     # no audio  (REQUIRED by Vicon docs)
        '-write_tmcd', '0',        # no timecode  (REQUIRED by Vicon docs)
        '-f', 'mov',
        output_path,
    ]
    return cmd


def build_redline_cmd(
    input_path: str,
    output_path: str,
    quality: int = 4,           # REDline --quality 1-9 (1=best)
    scale_factor: int = 1,
    redline_exe: str = 'REDline',
    colour_science: str = 'REDWideGamutRGB',
) -> List[str]:
    """
    Build REDline command to transcode R3D → MJPEG MOV.

    REDline gives access to the full RED RAW pipeline.
    We output to a high-quality MJPEG MOV.
    """
    # REDline outputs to a directory; we name the file via --outfilename
    out_dir  = str(Path(output_path).parent)
    out_name = Path(output_path).stem   # REDline adds its own extension

    cmd = [
        redline_exe,
        '--i',        input_path,
        '--outDir',   out_dir,
        '--outFilename', out_name,
        '--format',   'MOV',
        '--codec',    'MJPEG',
        '--quality',  str(quality),
        '--noaudio',
    ]

    if scale_factor == 2:
        cmd += ['--resizeX', '0.5', '--resizeY', '0.5']
    elif scale_factor == 4:
        cmd += ['--resizeX', '0.25', '--resizeY', '0.25']

    return cmd


# ============================================================================
#  WORKER THREAD
# ============================================================================

class TranscodeWorker(QThread):
    log_line   = Signal(str)
    progress   = Signal(int, int)   # current, total
    file_done  = Signal(int, bool)  # index, success
    finished   = Signal(int, int)   # done_count, error_count

    def __init__(self, jobs: list, settings: dict):
        super().__init__()
        self.jobs     = jobs      # list of (input_path, output_path)
        self.settings = settings
        self._abort   = False

    def abort(self):
        self._abort = True

    def run(self):
        done = errors = 0
        total = len(self.jobs)

        for idx, (inp, out) in enumerate(self.jobs):
            if self._abort:
                self.log_line.emit('[ABORTED]')
                break

            self.log_line.emit(f'\n[{idx+1}/{total}]  {Path(inp).name}')
            self.log_line.emit(f'         → {out}')
            self.progress.emit(idx, total)

            # Build command
            backend  = self.settings['backend']
            scale    = self.settings['scale_factor']
            os.makedirs(Path(out).parent, exist_ok=True)

            if backend == 'redline':
                redline = self.settings['redline_exe']
                cmd = build_redline_cmd(
                    inp, out,
                    quality=self.settings['redline_quality'],
                    scale_factor=scale,
                    redline_exe=redline,
                )
            else:
                ffmpeg = self.settings['ffmpeg_exe']
                cmd = build_ffmpeg_cmd(
                    inp, out,
                    quality=self.settings['ffmpeg_quality'],
                    scale_factor=scale,
                    ffmpeg_exe=ffmpeg,
                )

            self.log_line.emit('  CMD: ' + ' '.join(f'"{c}"' if ' ' in c else c
                                                      for c in cmd))

            try:
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding='utf-8',
                    errors='replace',
                )
                for line in proc.stdout:
                    line = line.rstrip()
                    if line:
                        # FFmpeg is very verbose — filter to key lines
                        if any(k in line for k in
                               ['frame=', 'fps=', 'error', 'Error',
                                'warning', 'Warning', 'Output #',
                                'Stream #', 'Press']):
                            self.log_line.emit('  ' + line)
                proc.wait()
                success = (proc.returncode == 0)
            except FileNotFoundError as e:
                self.log_line.emit(f'  ERROR: {e}')
                success = False
            except Exception as e:
                self.log_line.emit(f'  ERROR: {e}')
                success = False

            if success:
                done += 1
                self.log_line.emit(f'  ✓  Done')
            else:
                errors += 1
                self.log_line.emit(f'  ✗  FAILED (return code {proc.returncode if "proc" in dir() else "?"})')

            self.file_done.emit(idx, success)

        self.progress.emit(total, total)
        self.finished.emit(done, errors)


# ============================================================================
#  DRAG-AND-DROP FILE LIST
# ============================================================================

class DropListWidget(QListWidget):
    """QListWidget that accepts drag-and-drop of R3D files."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DropOnly)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)

    def dragEnterEvent(self, e: QDragEnterEvent):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dragMoveEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e: QDropEvent):
        for url in e.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith('.r3d'):
                self._add_if_new(path)
        e.acceptProposedAction()

    def _add_if_new(self, path: str):
        existing = [self.item(i).data(Qt.UserRole)
                    for i in range(self.count())]
        if path not in existing:
            item = QListWidgetItem(Path(path).name)
            item.setData(Qt.UserRole, path)
            item.setToolTip(path)
            self.addItem(item)

    def all_paths(self) -> List[str]:
        return [self.item(i).data(Qt.UserRole)
                for i in range(self.count())]


# ============================================================================
#  MAIN WINDOW
# ============================================================================

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('R3D → MJPEG  |  Vicon VideoCalibrator Prep')
        self.setMinimumSize(820, 740)
        self.resize(920, 800)
        self._worker = None
        self._redline = find_redline()
        self._ffmpeg  = find_ffmpeg()
        self._build_ui()
        self._detect_backends()

    # ── UI ────────────────────────────────────────────────────────────────

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(22, 18, 22, 18)
        root.setSpacing(12)

        # Header
        hdr = QWidget()
        hl = QVBoxLayout(hdr); hl.setContentsMargins(0,0,0,0); hl.setSpacing(2)
        t = QLabel('R3D  →  MJPEG  MOV'); t.setObjectName('title_lbl')
        s = QLabel('Vicon VideoCalibrator transcode prep  ·  MJPEG · No audio · No timecode')
        s.setObjectName('sub_lbl')
        hl.addWidget(t); hl.addWidget(s)
        root.addWidget(hdr)

        div = QFrame(); div.setObjectName('div'); div.setFrameShape(QFrame.HLine)
        root.addWidget(div)

        # Input files
        inp = QGroupBox('Input R3D Files  (drag & drop or Browse)')
        il = QVBoxLayout(inp); il.setSpacing(6)
        self.file_list = DropListWidget()
        self.file_list.setMinimumHeight(130)

        btn_row = QHBoxLayout()
        add_btn = QPushButton('Browse…')
        add_btn.clicked.connect(self._browse_inputs)
        self.rem_btn = QPushButton('Remove Selected')
        self.rem_btn.setObjectName('danger_btn')
        self.rem_btn.clicked.connect(self._remove_selected)
        clr_btn = QPushButton('Clear All')
        clr_btn.setObjectName('danger_btn')
        clr_btn.clicked.connect(self.file_list.clear)
        btn_row.addWidget(add_btn)
        btn_row.addWidget(self.rem_btn)
        btn_row.addWidget(clr_btn)
        btn_row.addStretch()
        il.addWidget(self.file_list)
        il.addLayout(btn_row)
        root.addWidget(inp)

        # Output folder
        out_grp = QGroupBox('Output Folder')
        ol = QVBoxLayout(out_grp); ol.setSpacing(6)
        out_row = QHBoxLayout()
        self.out_edit = QLineEdit()
        self.out_edit.setPlaceholderText(
            'Folder where .mov files will be written…')
        out_browse = QPushButton('Browse…')
        out_browse.setFixedWidth(85)
        out_browse.clicked.connect(self._browse_output)
        out_row.addWidget(self.out_edit)
        out_row.addWidget(out_browse)
        ol.addLayout(out_row)
        root.addWidget(out_grp)

        # Settings
        sgrp = QGroupBox('Transcode Settings')
        sl = QHBoxLayout(sgrp); sl.setSpacing(24)

        # Backend
        bc = QVBoxLayout()
        bc.addWidget(QLabel('Backend'))
        self.backend_combo = QComboBox()
        self.backend_combo.addItem('FFmpeg  (universal)', 'ffmpeg')
        self.backend_combo.addItem('REDline  (RED RAW pipeline)', 'redline')
        self.backend_combo.currentIndexChanged.connect(self._on_backend_change)
        bc.addWidget(self.backend_combo)
        self.backend_status = QLabel('')
        self.backend_status.setObjectName('sub_lbl')
        bc.addWidget(self.backend_status)
        sl.addLayout(bc)

        # Quality
        qc = QVBoxLayout()
        qc.addWidget(QLabel('MJPEG Quality'))
        self.quality_spin = QSpinBox()
        self.quality_spin.setRange(1, 15)
        self.quality_spin.setValue(2)
        self.quality_spin.setFixedWidth(70)
        qh = QLabel('FFmpeg: 1=best · 2=near-lossless · 5=good')
        qh.setObjectName('sub_lbl')
        qc.addWidget(self.quality_spin)
        qc.addWidget(qh)
        sl.addLayout(qc)

        # Scale
        sc2 = QVBoxLayout()
        sc2.addWidget(QLabel('Spatial Subsample'))
        self.scale_combo = QComboBox()
        self.scale_combo.addItem('Full resolution  (1×)', 1)
        self.scale_combo.addItem('Half size  (2×)',       2)
        self.scale_combo.addItem('Quarter size  (4×)',    4)
        sch = QLabel('Per --video-subsample-factor in VideoCalibrator')
        sch.setObjectName('sub_lbl')
        sc2.addWidget(self.scale_combo)
        sc2.addWidget(sch)
        sl.addLayout(sc2)

        # Executable override
        ec = QVBoxLayout()
        ec.addWidget(QLabel('Executable Path  (optional override)'))
        exe_row = QHBoxLayout()
        self.exe_edit = QLineEdit()
        self.exe_edit.setPlaceholderText('Auto-detected…')
        exe_browse = QPushButton('…')
        exe_browse.setFixedWidth(32)
        exe_browse.clicked.connect(self._browse_exe)
        exe_row.addWidget(self.exe_edit)
        exe_row.addWidget(exe_browse)
        ec.addLayout(exe_row)
        sl.addLayout(ec)
        sl.addStretch()
        root.addWidget(sgrp)

        # Go button + progress
        gr = QHBoxLayout()
        self.abort_btn = QPushButton('■  ABORT')
        self.abort_btn.setFixedHeight(42)
        self.abort_btn.setFixedWidth(110)
        self.abort_btn.setObjectName('danger_btn')
        self.abort_btn.setEnabled(False)
        self.abort_btn.clicked.connect(self._abort)
        self.go_btn = QPushButton('▶   TRANSCODE')
        self.go_btn.setObjectName('go_btn')
        self.go_btn.setFixedHeight(42)
        self.go_btn.clicked.connect(self._run)
        gr.addStretch()
        gr.addWidget(self.abort_btn)
        gr.addSpacing(8)
        gr.addWidget(self.go_btn)
        gr.addStretch()
        root.addLayout(gr)

        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress.setFixedHeight(5)
        root.addWidget(self.progress)

        # Log
        lg = QGroupBox('Transcode Log')
        ll = QVBoxLayout(lg)
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(160)
        self.log.setPlaceholderText(
            'Transcode output will appear here.\n\n'
            'Output spec:\n'
            '  • Codec:     MJPEG (Motion JPEG)\n'
            '  • Audio:     Stripped  (-an)\n'
            '  • Timecode:  Stripped  (-write_tmcd 0)\n'
            '  • Container: QuickTime .mov\n\n'
            'All files must have matching frame indices for VideoCalibrator sync.'
        )
        ll.addWidget(self.log)
        self.status_lbl = QLabel('')
        ll.addWidget(self.status_lbl)
        root.addWidget(lg)

    # ── Backend detection ─────────────────────────────────────────────────

    def _detect_backends(self):
        lines = []
        if self._ffmpeg:
            lines.append(f'FFmpeg: {self._ffmpeg}')
        else:
            lines.append('FFmpeg: NOT FOUND  (install from ffmpeg.org or add to PATH)')
        if self._redline:
            lines.append(f'REDline: {self._redline}')
        else:
            lines.append('REDline: not found  (optional)')
        self.log.setPlaceholderText('\n'.join(lines) + '\n\n' +
                                    self.log.placeholderText())
        self._on_backend_change()

    def _on_backend_change(self):
        backend = self.backend_combo.currentData()
        if backend == 'ffmpeg':
            if self._ffmpeg:
                self.backend_status.setText(f'✓  {self._ffmpeg}')
                self.backend_status.setObjectName('ok_lbl')
            else:
                self.backend_status.setText('✗  Not found — install FFmpeg')
                self.backend_status.setObjectName('err_lbl')
            self.quality_spin.setRange(1, 31)
            self.quality_spin.setValue(2)
        else:
            if self._redline:
                self.backend_status.setText(f'✓  {self._redline}')
                self.backend_status.setObjectName('ok_lbl')
            else:
                self.backend_status.setText('✗  Not found — check install path')
                self.backend_status.setObjectName('err_lbl')
            self.quality_spin.setRange(1, 9)
            self.quality_spin.setValue(4)
        self.backend_status.setStyle(self.backend_status.style())

    # ── File pickers ──────────────────────────────────────────────────────

    def _browse_inputs(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, 'Select R3D files', '',
            'RED RAW (*.r3d *.R3D);;All files (*.*)')
        for p in paths:
            self.file_list._add_if_new(p)

    def _browse_output(self):
        d = QFileDialog.getExistingDirectory(
            self, 'Select output folder',
            self.out_edit.text() or str(Path.home()))
        if d: self.out_edit.setText(d)

    def _browse_exe(self):
        path, _ = QFileDialog.getOpenFileName(
            self, 'Select executable', '',
            'Executables (*.exe);;All files (*.*)')
        if path: self.exe_edit.setText(path)

    def _remove_selected(self):
        for item in self.file_list.selectedItems():
            self.file_list.takeItem(self.file_list.row(item))

    # ── Validation & run ──────────────────────────────────────────────────

    def _validate(self) -> bool:
        if self.file_list.count() == 0:
            self._set_status('Add at least one R3D file.', 'err')
            return False
        if not self.out_edit.text().strip():
            self._set_status('Select an output folder.', 'err')
            return False
        backend = self.backend_combo.currentData()
        exe = self.exe_edit.text().strip()
        if backend == 'ffmpeg':
            ff = exe or self._ffmpeg
            if not ff:
                self._set_status(
                    'FFmpeg not found. Install it or set path manually.', 'err')
                return False
        else:
            rl = exe or self._redline
            if not rl:
                self._set_status(
                    'REDline not found. Check install or set path manually.', 'err')
                return False
        return True

    def _run(self):
        if not self._validate(): return

        inputs = self.file_list.all_paths()
        out_dir = self.out_edit.text().strip()
        backend = self.backend_combo.currentData()
        exe_override = self.exe_edit.text().strip()

        # Build job list
        jobs = []
        for inp in inputs:
            stem = Path(inp).stem
            out = os.path.join(out_dir, stem + '.mov')
            jobs.append((inp, out))

        settings = {
            'backend':          backend,
            'ffmpeg_exe':       exe_override or self._ffmpeg or 'ffmpeg',
            'redline_exe':      exe_override or self._redline or 'REDline',
            'ffmpeg_quality':   self.quality_spin.value(),
            'redline_quality':  self.quality_spin.value(),
            'scale_factor':     self.scale_combo.currentData(),
        }

        self.log.clear()
        self._set_status('')
        self.go_btn.setEnabled(False)
        self.abort_btn.setEnabled(True)
        self.progress.setRange(0, len(jobs))
        self.progress.setValue(0)

        self._worker = TranscodeWorker(jobs, settings)
        self._worker.log_line.connect(self._append_log)
        self._worker.progress.connect(
            lambda cur, tot: self.progress.setValue(cur))
        self._worker.file_done.connect(self._on_file_done)
        self._worker.finished.connect(self._on_done)
        self._worker.start()

    def _abort(self):
        if self._worker:
            self._worker.abort()
        self.abort_btn.setEnabled(False)

    def _on_file_done(self, idx: int, success: bool):
        item = self.file_list.item(idx)
        if item:
            item.setForeground(QColor(SUCCESS if success else ERR))

    def _on_done(self, done: int, errors: int):
        self.go_btn.setEnabled(True)
        self.abort_btn.setEnabled(False)
        self.progress.setValue(self.progress.maximum())
        if errors == 0:
            self._set_status(
                f'✓  {done} file(s) transcoded successfully.', 'ok')
        else:
            self._set_status(
                f'⚠  {done} succeeded, {errors} failed — see log.', 'warn')

    def _append_log(self, text: str):
        self.log.append(text)
        self.log.verticalScrollBar().setValue(
            self.log.verticalScrollBar().maximum())

    def _set_status(self, msg: str, level: str = 'ok'):
        obj = {'ok': 'ok_lbl', 'err': 'err_lbl', 'warn': 'warn_lbl'}.get(level, 'ok_lbl')
        self.status_lbl.setText(msg)
        self.status_lbl.setObjectName(obj)
        self.status_lbl.setStyle(self.status_lbl.style())


# ============================================================================
#  ENTRY POINT
# ============================================================================

def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    app.setStyleSheet(STYLE)

    pal = QPalette()
    pal.setColor(QPalette.Window,          QColor(DARK_BG))
    pal.setColor(QPalette.WindowText,      QColor(TEXT_PRI))
    pal.setColor(QPalette.Base,            QColor(PANEL_BG))
    pal.setColor(QPalette.AlternateBase,   QColor(DARK_BG))
    pal.setColor(QPalette.Text,            QColor(TEXT_PRI))
    pal.setColor(QPalette.Button,          QColor(PANEL_BG))
    pal.setColor(QPalette.ButtonText,      QColor(TEXT_SEC))
    pal.setColor(QPalette.Highlight,       QColor('#1f3a6b'))
    pal.setColor(QPalette.HighlightedText, QColor(TEXT_PRI))
    app.setPalette(pal)

    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
