# SPDX-License-Identifier: MIT
# -*- coding: utf-8 -*-
"""
main.py → 단일 실행파일(.exe) 빌드 스크립트.

사용법:
    python build_exe.py              # onefile (단일 exe, 배포 용이)
    python build_exe.py --onedir     # 폴더 통째 (시작 빠름)
    python build_exe.py --debug      # 콘솔창 표시 (오류 진단용)
    python build_exe.py --upx        # UPX 압축 활성화 (추가 ~50% 절감)
    python build_exe.py --clean-cache         # 빌드 전 build/, dist/ 삭제
    python build_exe.py --rebuild-venv        # 빌드 전용 venv 재생성

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
크기 최적화 전략
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  [핵심 원인] 빌드 venv(rbcks) 에 torch, llvmlite, scipy, opencv 등
              대형 ML 패키지가 함께 설치돼 있어서 PyInstaller 가
              이를 포함 → 2.4 GB 이상 발생.

  [해결책] requirements.txt 5개 패키지 + PyInstaller 만 설치된
            전용 빌드 venv (.build_venv/) 를 생성하고
            그 환경에서 PyInstaller 를 실행한다.

  [기대 크기]
    - onefile: 약 350~480 MB (torch/llvmlite 제외)
    - onedir 폴더 합계: 약 200~300 MB
    - --upx 추가 시: onefile 약 180~260 MB
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import venv as _venv_mod
from pathlib import Path

from release_metadata import write_windows_version_info


HERE      = Path(__file__).resolve().parent
ENTRY     = HERE / "main.py"
APP_NAME  = "FORECAST-SW"
REQ_FILE  = HERE / "requirements.txt"

# ── 플랫폼별 venv 레이아웃 / 실행파일 확장자 ──────────────────────────────
#   Windows: <venv>/Scripts/python.exe,  산출물 <name>.exe
#   POSIX  : <venv>/bin/python,          산출물 <name>
_VENV_BIN = "Scripts" if os.name == "nt" else "bin"
_EXE_EXT  = ".exe" if os.name == "nt" else ""


def _venv_python(venv: Path) -> Path:
    return venv / _VENV_BIN / f"python{_EXE_EXT}"


# pip 배포명과 import 모듈명이 다른 패키지 매핑 (requirements.txt 기준)
_IMPORT_NAME_MAP = {
    "pyqt5": "PyQt5",
    "pillow": "PIL",
    "pyinstaller": "PyInstaller",
}


def _requirements_import_names(req_file: Path) -> list[str]:
    """requirements.txt 각 줄의 배포 패키지명을 import 모듈명으로 변환해 반환."""
    if not req_file.exists():
        return []
    names = []
    for line in req_file.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        pkg = re.split(r"[<>=!~\[; ]", line, 1)[0].strip()
        if pkg:
            names.append(_IMPORT_NAME_MAP.get(pkg.lower(), pkg))
    return names


def _venv_ready(python: Path) -> bool:
    """venv 에 requirements.txt 의 모든 패키지 + PyInstaller 가 설치되어
    재사용 가능한지 확인.

    과거에는 PyQt5 + PyInstaller 만 확인했기 때문에, requirements.txt 에
    pyvista/pyvistaqt/vtk 등이 나중에 추가되거나 설치가 중간에 실패해도
    기존(불완전한) venv 를 그대로 재사용해버려 — 해당 패키지가 exe 에서
    누락된 채 빌드되고 실행 시 ModuleNotFoundError 가 나는 문제가 있었다.
    """
    if not python.exists():
        return False
    modules = _requirements_import_names(REQ_FILE) + ["PyInstaller"]
    if not modules:
        modules = ["PyInstaller", "PyQt5"]
    code = "; ".join(f"import {m}" for m in modules)
    r = subprocess.run(
        [str(python), "-c", code],
        capture_output=True,
    )
    return r.returncode == 0

# PyInstaller Qt hook 이 QLibraryInfo 를 subprocess 로 조회할 때
# 경로에 한글이 포함되면 '?????' 로 깨져 plugins 디렉터리를 찾지 못한다.
# → 홈 디렉터리(영문 경로) 아래에 빌드 전용 venv 를 생성한다.
BUILD_VENV = Path.home() / ".carboncalc_build_venv"
_OLD_VENV  = HERE / ".build_venv"   # 이전 위치 (한글 경로) — 자동 정리

_ICON_CANDIDATES = (
    HERE / "icon.ico",
    HERE.parent / "previous_application" / "icon.ico",
)


def find_icon() -> Path | None:
    for p in _ICON_CANDIDATES:
        if p.exists():
            return p
    return None


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build .exe for main.py")
    p.add_argument("--onedir", action="store_true",
                   help="Build as a folder instead of a single file.")
    p.add_argument("--debug", action="store_true",
                   help="Show the console window (for debugging).")
    p.add_argument("--upx", action="store_true",
                   help="Enable UPX compression (~50%% smaller; may trigger antivirus false positives).")
    p.add_argument("--clean-cache", action="store_true",
                   help="Delete build/ and dist/ before building.")
    p.add_argument("--rebuild-venv", action="store_true",
                   help="Force re-creation of the dedicated build venv.")
    return p.parse_args()


def clean_build_artifacts() -> None:
    for name in ("build", "dist"):
        path = HERE / name
        if path.exists():
            print(f"[clean] {path}")
            shutil.rmtree(path, ignore_errors=True)


# ─────────────────────────── 빌드 전용 venv ───────────────────────────

def ensure_build_venv(rebuild: bool = False) -> Path:
    """requirements.txt 패키지 + PyInstaller 만 설치된 전용 venv 를 준비한다.

    첫 실행 시 패키지 다운로드가 있어 몇 분 소요된다.
    이후 실행은 venv 에 PyInstaller/PyQt5 가 갖춰져 있으면 즉시 재사용한다.
    (설치가 중단돼 불완전한 venv 는 자동으로 패키지를 마저 설치한다.)
    """
    python = _venv_python(BUILD_VENV)

    # 이전 위치(한글 경로)에 남아 있는 venv 자동 정리
    if _OLD_VENV.exists():
        print(f"[env] Removing previous build venv (non-ASCII path): {_OLD_VENV}")
        shutil.rmtree(_OLD_VENV, ignore_errors=True)

    if rebuild and BUILD_VENV.exists():
        print(f"[env] Removing existing build venv: {BUILD_VENV}")
        shutil.rmtree(BUILD_VENV, ignore_errors=True)

    if not python.exists():
        print(f"[env] Creating the dedicated build venv (first run, takes a few minutes)...")
        print(f"       location: {BUILD_VENV}")
        _venv_mod.create(str(BUILD_VENV), with_pip=True, clear=False)

    if not python.exists():
        sys.exit(f"[error] Failed to create the build venv interpreter: {python}")

    # pip 보장 (일부 배포판은 ensurepip 필요)
    subprocess.run(
        [str(python), "-m", "ensurepip", "--upgrade"],
        capture_output=True,
    )

    if _venv_ready(python):
        print(f"[env] Reusing existing build venv: {BUILD_VENV}")
        return BUILD_VENV

    if not REQ_FILE.exists():
        sys.exit(f"[error] requirements.txt not found: {REQ_FILE}")

    print("[env] Upgrading pip...")
    subprocess.run(
        [str(python), "-m", "pip", "install", "--quiet", "--upgrade", "pip"],
        check=True,
    )
    print(f"[env] Installing packages from requirements.txt...")
    print(f"       ({REQ_FILE})")
    subprocess.run(
        [str(python), "-m", "pip", "install", "--quiet", "-r", str(REQ_FILE)],
        check=True,
    )
    print("[env] Installing PyInstaller...")
    subprocess.run(
        [str(python), "-m", "pip", "install", "--quiet", "pyinstaller"],
        check=True,
    )
    print("[env] Build environment ready.")
    return BUILD_VENV


# ─────────────────────────── spec 파일 생성 ───────────────────────────

# raw 문자열: {}는 f-string 이 아닌 spec 파일 코드로 그대로 출력됨
_SPEC_ANALYSIS = r"""# -*- mode: python ; coding: utf-8 -*-
# Auto-generated by build_exe.py — do not edit manually.

import os
from PyInstaller.utils.hooks import (
    collect_dynamic_libs, collect_submodules, collect_data_files,
)

block_cipher = None

# ── PyQt5 바이너리: 전체 수집 후 미사용 DLL 제거 ─────────────────────────────
# collect_dynamic_libs 는 PyQt5 패키지 디렉터리 내 DLL 만 반환 (2-튜플).
_EXCL_DLL = {
    # OpenGL/EGL 계열 DLL은 VTK/PyVista 3D 렌더링 fallback에 필요할 수 있어 보존한다.
    'qt5quick.dll', 'qt5qml.dll', 'qt5qmlmodels.dll', 'qt5qmlworkerscript.dll',
    'qt5designer.dll', 'qt5xmlpatterns.dll',
    'qt5location.dll', 'qt5multimedia.dll', 'qt5multimediaquick.dll',
    'qt5sql.dll', 'qt5bluetooth.dll',
    'qt5quick3d.dll', 'qt5quick3druntimerender.dll',
    'qt5quick3dassetimporter.dll', 'qt5quick3dutils.dll',
}
_EXCL_DIR = {
    'qml', 'sqldrivers', 'assetimporters', 'geoservices',
    'geometryloaders', 'sceneparsers', 'renderers', 'playlistformats',
}

def _keep_bin(src):
    if os.path.basename(src).lower() in _EXCL_DLL:
        return False
    parts = src.replace(os.sep, '/').lower().split('/')
    return not any(p in _EXCL_DIR for p in parts)

# collect_dynamic_libs 는 (src_path, dest_dir) 2-튜플을 반환한다.
_qt5_binaries = [
    (src, dest) for src, dest in collect_dynamic_libs('PyQt5')
    if _keep_bin(src)
]

# ── conda 파이썬 대응: Library\bin 의 DLL 동봉 ──────────────────────────────
# conda 배포판은 _ctypes(ffi.dll)·pyexpat(libexpat.dll)·_ssl·_sqlite3 등이 의존하는
# DLL 을 <base_prefix>\Library\bin 에 둔다. PyInstaller 는 이 경로를 검색하지 않아
# 그대로 빌드하면 실행 시 "DLL load failed while importing _ctypes" 로 죽는다.
# 표준 확장모듈(.pyd)의 import 테이블을 훑어 실제로 필요한 DLL 만 골라 담는다.
import glob as _glob
import sys as _sys

def _collect_conda_dlls():
    _base = getattr(_sys, 'base_prefix', _sys.prefix)
    _libbin = os.path.join(_base, 'Library', 'bin')
    _dlls = os.path.join(_base, 'DLLs')
    if not (os.path.isdir(_libbin) and os.path.isdir(_dlls)):
        return []                      # conda 가 아니면 할 일 없음
    _avail = {os.path.basename(p).lower(): p
              for p in _glob.glob(os.path.join(_libbin, '*.dll'))}
    try:
        from PyInstaller.depend import bindepend as _bd
    except Exception:
        _bd = None
    _needed = set()
    if _bd is not None:
        for _pyd in _glob.glob(os.path.join(_dlls, '*.pyd')):
            try:
                _imports = _bd.get_imports(_pyd)
            except Exception:
                continue
            for _imp in _imports:
                _nm = _imp if isinstance(_imp, str) else _imp[0]
                _low = os.path.basename(_nm).lower()
                if _low in _avail:
                    _needed.add(_low)
    if not _needed:
        # bindepend 를 못 쓰면 알려진 필수 DLL 로 대체
        _needed = {n for n in ('ffi.dll', 'ffi-8.dll', 'libffi-8.dll', 'libexpat.dll',
                               'libcrypto-3-x64.dll', 'libssl-3-x64.dll', 'sqlite3.dll',
                               'libbz2.dll', 'liblzma.dll') if n in _avail}
    _out = [(_avail[n], '.') for n in sorted(_needed)]
    print('[spec] conda DLL %d개 동봉: %s' % (len(_out), ', '.join(sorted(_needed))))
    return _out

_conda_binaries = _collect_conda_dlls()

# ── matplotlib 데이터: 폰트·샘플 제외 (약 8.4 MB) ────────────────────────────
_SKIP_MPL = ('matplotlib/mpl-data/fonts/', 'matplotlib/mpl-data/sample_data/')
_mpl_datas = [
    (src, dest) for src, dest in collect_data_files('matplotlib')
    if not any(dest.replace(os.sep, '/').startswith(p) for p in _SKIP_MPL)
]

# ── JSON 데이터 파일 동봉 (프로젝트 루트에 존재하는 경우만) ─────────────────────────
_HERE_PATH = __HERE__
_JSON_NAMES = [
    'carbon1_species_data.json', 'carbon2_species_data.json', 'species_data.json',
    'translations_ko_en.json',  # UI 한/영 번역표 — exe 옆에 두면 재빌드 없이 수정 반영
]
_json_datas = [
    (os.path.join(_HERE_PATH, _jn), '.')
    for _jn in _JSON_NAMES
    if os.path.exists(os.path.join(_HERE_PATH, _jn))
]

# ── Analysis ─────────────────────────────────────────────────────────────────
a = Analysis(
    [__ENTRY__],
    pathex=[__HERE__],
    binaries=_qt5_binaries + _conda_binaries,
    datas=_mpl_datas + _json_datas,
    hiddenimports=(
        collect_submodules('carbon_calculator')
        + collect_submodules('openpyxl')
        + collect_submodules('PIL')
        + [
            'matplotlib.backends.backend_qt5agg',
            'matplotlib.backends.backend_qtagg',
            'PyQt5.sip',
            'PIL.Image',
            'PIL.PngImagePlugin',
            'PIL.ImageDraw',
            'qtpy',
            'pyvista',
            'pyvistaqt',
            'vtkmodules.qt.QVTKRenderWindowInteractor',
            'vtkmodules.vtkInteractionStyle',
            'vtkmodules.vtkRenderingFreeType',
            'vtkmodules.vtkRenderingOpenGL2',
        ]
    ),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'PyQt5.QtWebEngineWidgets', 'PyQt5.QtWebEngine', 'PyQt5.QtWebEngineCore',
        'PyQt5.QtQuick', 'PyQt5.QtQml', 'PyQt5.QtQuickWidgets',
        'PyQt5.QtQuick3D', 'PyQt5.QtQuickControls2',
        'PyQt5.QtDesigner',
        'PyQt5.QtMultimedia', 'PyQt5.QtMultimediaWidgets',
        'PyQt5.QtLocation', 'PyQt5.QtPositioning',
        'PyQt5.QtNetwork', 'PyQt5.QtNetworkAuth', 'PyQt5.QtSql',
        'PyQt5.Qt3DCore', 'PyQt5.Qt3DRender', 'PyQt5.Qt3DInput',
        'PyQt5.Qt3DLogic', 'PyQt5.Qt3DAnimation', 'PyQt5.Qt3DExtras',
        'PyQt5.QtBluetooth', 'PyQt5.QtXmlPatterns', 'PyQt5.QtNfc',
        'PyQt5.QtRemoteObjects', 'PyQt5.QtSerialPort', 'PyQt5.QtSensors',
        'PyQt5.QtTextToSpeech', 'PyQt5.QtVirtualKeyboard',
        'PyQt5.QtPurchasing', 'PyQt5.QtDataVisualization', 'PyQt5.QtCharts',
        'PySide2', 'PySide6', 'PyQt6',
        'torch', 'torchvision', 'torchaudio',
        'cv2', 'opencv', 'sklearn', 'scipy', 'numba', 'llvmlite',
        'tensorflow', 'keras', 'lightgbm', 'xgboost', 'catboost',
        'ultralytics', 'IPython', 'jupyter',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
"""

_SPEC_ONEFILE_EXE = r"""
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name=__APP_NAME__,
    debug=__CONSOLE__,
    bootloader_ignore_signals=False,
    strip=False,
    upx=__UPX__,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=__CONSOLE__,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    __VERSION_LINE__
    __ICON_LINE__
)
"""

_SPEC_ONEDIR_EXE = r"""
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=__APP_NAME__,
    debug=__CONSOLE__,
    strip=False,
    upx=__UPX__,
    upx_exclude=[],
    console=__CONSOLE__,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    __VERSION_LINE__
    __ICON_LINE__
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=__UPX__,
    upx_exclude=[],
    name=__APP_NAME__,
)
"""


def _write_spec(onedir: bool, debug: bool, upx: bool) -> Path:
    """spec 파일을 생성하고 경로를 반환한다."""
    icon = find_icon()
    icon_line = f"icon={repr(str(icon))}," if icon else "# icon=None"
    spec_dir = HERE / "build"
    version_file = write_windows_version_info(
        spec_dir,
        internal_name=APP_NAME,
        original_filename=f"{APP_NAME}{_EXE_EXT}",
        file_description="FORECAST-SW Assessment Application",
    )
    version_line = f"version={repr(str(version_file))}," if version_file else "# version=None"

    analysis = (
        _SPEC_ANALYSIS
        .replace("__ENTRY__", repr(str(ENTRY)))
        .replace("__HERE__",  repr(str(HERE)))
    )

    exe_tmpl = _SPEC_ONEDIR_EXE if onedir else _SPEC_ONEFILE_EXE
    exe_section = (
        exe_tmpl
        .replace("__APP_NAME__", repr(APP_NAME))
        .replace("__CONSOLE__",  "True" if debug else "False")
        .replace("__UPX__",      "True" if upx else "False")
        .replace("__VERSION_LINE__", version_line)
        .replace("__ICON_LINE__", icon_line)
    )

    spec_dir.mkdir(parents=True, exist_ok=True)
    spec_path = spec_dir / f"{APP_NAME}.spec"
    spec_path.write_text(analysis + exe_section, encoding="utf-8")
    return spec_path


# ─────────────────────────── 진입점 ───────────────────────────

def main() -> int:
    args = parse_args()

    if not ENTRY.exists():
        sys.exit(f"[error] Entry point not found: {ENTRY}")

    if args.clean_cache:
        clean_build_artifacts()

    build_venv = ensure_build_venv(rebuild=args.rebuild_venv)

    spec_path = _write_spec(onedir=args.onedir, debug=args.debug, upx=args.upx)

    python_exe = _venv_python(build_venv)
    if not python_exe.exists():
        sys.exit(f"[error] Build venv interpreter not found: {python_exe}")

    print()
    print("=" * 70)
    print("Starting PyInstaller build")
    print(f"  entry point: {ENTRY}")
    print(f"  spec:        {spec_path}")
    print(f"  app name:    {APP_NAME}")
    print(f"  build env:   {build_venv}")
    print(f"  mode:        {'onedir (folder)' if args.onedir else 'onefile (single file)'}")
    print(f"  console:     {'shown' if args.debug else 'hidden (GUI)'}")
    print(f"  UPX:         {'enabled' if args.upx else 'disabled'}")
    icon = find_icon()
    print(f"  icon:        {icon if icon else '(none)'}")
    print("=" * 70)

    result = subprocess.run(
        [
            str(python_exe), "-m", "PyInstaller",
            str(spec_path),
            "--noconfirm",
            "--clean",
            f"--workpath={HERE / 'build'}",
            f"--distpath={HERE / 'dist'}",
        ],
        cwd=str(HERE),
    )

    if result.returncode != 0:
        print()
        print("=" * 70)
        print("[failed] The PyInstaller build failed.")
        print("       Check the log above for the cause.")
        print("=" * 70)
        return 1

    # ── 산출물 크기 안내 ────────────────────────────────────────────
    dist_dir = HERE / "dist"
    if args.onedir:
        out     = dist_dir / APP_NAME / f"{APP_NAME}{_EXE_EXT}"
        out_dir = dist_dir / APP_NAME
    else:
        out     = dist_dir / f"{APP_NAME}{_EXE_EXT}"
        out_dir = None

    print()
    print("=" * 70)
    if out.exists():
        exe_mb = out.stat().st_size / 1048576
        print(f"[success] Build complete: {out}")
        print(f"       executable size: {exe_mb:.1f} MB")
        if out_dir:
            dir_mb = sum(f.stat().st_size for f in out_dir.rglob("*") if f.is_file()) / 1048576
            print(f"       folder total: {dir_mb:.1f} MB")
            print(f"       To distribute, copy the whole folder {out_dir}.")
        else:
            print("       Double-click this file to run the application.")
    else:
        print(f"[failed] Build output not found: {out}")
        print("       Check the logs under build/.")
    print("=" * 70)

    return 0 if out.exists() else 1


if __name__ == "__main__":
    sys.exit(main())
