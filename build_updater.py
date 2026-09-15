# SPDX-License-Identifier: MIT
# -*- coding: utf-8 -*-
"""
updater_app.py -> FORECAST-SW-Equation-Library-Manager.exe build script
(self-contained).

FORECAST-SW의 **전체 소스(carbon_calculator + main.py + build_exe.py 등)를
library-manager executable 내부에 번들**한다. 따라서 빌드된
FORECAST-SW-Equation-Library-Manager.exe 는 소스 폴더 없이
단독으로 배포·실행할 수 있으며, 사용자는 통합 species_data.json 만 넣으면 새
FORECAST-SW.exe 를 빌드할 수 있다.

사용법:
    python build_updater.py              # onefile (기본)
    python build_updater.py --onedir     # 폴더형
    python build_updater.py --debug      # 콘솔창 표시
    python build_updater.py --upx        # UPX 압축
    python build_updater.py --clean-cache
    python build_updater.py --rebuild-venv

배포 방법:
    빌드된 FORECAST-SW-Equation-Library-Manager.exe 하나만 배포하면 된다.
    사용자 PC 에 Python 3.10+ 이 있으면 이 exe 로 재빌드까지 가능하고,
    Python 이 없어도 'JSON 적용' 모드로 기존 exe 옆에 데이터만 갱신할 수 있다.
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


HERE       = Path(__file__).resolve().parent
ENTRY      = HERE / "updater_app.py"
APP_NAME   = "FORECAST-SW-Equation-Library-Manager"
REQ_FILE   = HERE / "requirements.txt"
BUILD_VENV = Path.home() / ".carboncalc_build_venv"
_OLD_VENV  = HERE / ".build_venv"

# ── 플랫폼별 venv 레이아웃 / 실행파일 확장자 ──────────────────────────────
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

    build_exe.py 와 빌드 venv 를 공유하므로, 여기서도 PyQt5 + PyInstaller
    만 확인하면 requirements.txt 에 나중에 추가된 패키지(pyvista/pyvistaqt/
    vtk 등)가 누락된 채로 venv 가 "준비됨"으로 오판될 수 있다.
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

# ── Equation Library Manager에 번들할 소스 (FORECAST-SW 전체 코드 로직) ──
# 런타임에 _MEIPASS/bundled_src 로 풀려, manager가 이를 임시 작업폴더로 복사해 빌드한다.
_BUNDLE_ROOT_FILES = (
    "main.py",
    "build_exe.py", "release_metadata.py", "requirements.txt",
    "species_data.json",             # 기본 통합 데이터 (사용자 JSON 이 덮어씀)
    "translations_ko_en.json",       # UI 한/영 번역표 (사용자 JSON 이 덮어씀)
)
_CC_DIR = HERE / "carbon_calculator"

_ICON_CANDIDATES = (
    HERE / "icon.ico",
    HERE.parent / "previous_application" / "icon.ico",
)


def find_icon() -> Path | None:
    for p in _ICON_CANDIDATES:
        if p.exists():
            return p
    return None


def collect_bundled_datas() -> list[tuple[str, str]]:
    """FORECAST-SW 소스를 PyInstaller datas 형식 (src, dest) 로 수집.

    dest 'bundled_src' 는 런타임에 _MEIPASS/bundled_src 로 풀린다.
    """
    datas: list[tuple[str, str]] = []
    for fn in _BUNDLE_ROOT_FILES:
        p = HERE / fn
        if p.exists():
            datas.append((str(p), "bundled_src"))
        else:
            print(f"[warning] Bundled file missing: {p}")

    icon = find_icon()
    if icon:
        datas.append((str(icon), "bundled_src"))

    if not _CC_DIR.exists():
        sys.exit(f"[error] carbon_calculator package not found: {_CC_DIR}")
    # 하위 기능 패키지(tree_simulation 등)도 상대 디렉터리를 보존해 재귀적으로 번들한다.
    for py in sorted(_CC_DIR.rglob("*.py")):
        rel_parent = py.parent.relative_to(_CC_DIR).as_posix()
        dest = "bundled_src/carbon_calculator"
        if rel_parent != ".":
            dest += f"/{rel_parent}"
        datas.append((str(py), dest))

    return datas


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build the FORECAST-SW Equation Library Manager")
    p.add_argument("--onedir",        action="store_true", help="Build as a folder.")
    p.add_argument("--debug",         action="store_true", help="Show the console window.")
    p.add_argument("--upx",           action="store_true", help="Enable UPX compression.")
    p.add_argument("--clean-cache",   action="store_true", help="Delete build/ and dist/.")
    p.add_argument("--rebuild-venv",  action="store_true", help="Force re-creation of the build venv.")
    return p.parse_args()


def clean_build_artifacts() -> None:
    for name in ("build", "dist"):
        path = HERE / name
        if path.exists():
            print(f"[clean] {path}")
            shutil.rmtree(path, ignore_errors=True)


def ensure_build_venv(rebuild: bool = False) -> Path:
    """PyQt5 + PyInstaller 가 설치된 빌드 전용 venv 를 준비한다.

    build_exe.py 의 빌드 venv 와 동일한 위치를 공유한다.
    requirements.txt(PyQt5 포함)가 이미 설치돼 있으면 재사용한다.
    """
    python = _venv_python(BUILD_VENV)

    if _OLD_VENV.exists():
        print(f"[env] Removing previous build venv: {_OLD_VENV}")
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

    print("[env] Upgrading pip...")
    subprocess.run(
        [str(python), "-m", "pip", "install", "--quiet", "--upgrade", "pip"],
        check=True,
    )
    if REQ_FILE.exists():
        print(f"[env] Installing packages from requirements.txt...")
        subprocess.run(
            [str(python), "-m", "pip", "install", "--quiet", "-r", str(REQ_FILE)],
            check=True,
        )
    else:
        print("[env] Installing PyQt5...")
        subprocess.run(
            [str(python), "-m", "pip", "install", "--quiet", "PyQt5"],
            check=True,
        )
    print("[env] Installing PyInstaller...")
    subprocess.run(
        [str(python), "-m", "pip", "install", "--quiet", "pyinstaller"],
        check=True,
    )
    print("[env] Build environment ready.")
    return BUILD_VENV


# ─────────────────────────── spec 파일 ───────────────────────────

# Manager는 PyQt5 + 표준 라이브러리만 사용. matplotlib/openpyxl/PIL 등 불필요.
_SPEC_ANALYSIS = r"""# -*- mode: python ; coding: utf-8 -*-
# Auto-generated by build_updater.py — do not edit manually.

import os
from PyInstaller.utils.hooks import collect_dynamic_libs

block_cipher = None

_EXCL_DLL = {
    'opengl32sw.dll', 'd3dcompiler_47.dll',
    'libglesv2.dll', 'libegl.dll',
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

a = Analysis(
    [__ENTRY__],
    pathex=[__HERE__],
    binaries=_qt5_binaries + _conda_binaries,
    datas=__DATAS__,
    hiddenimports=['PyQt5.sip'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib', 'numpy', 'openpyxl', 'PIL', 'pandas',
        'PyQt5.QtWebEngineWidgets', 'PyQt5.QtWebEngine', 'PyQt5.QtWebEngineCore',
        'PyQt5.QtQuick', 'PyQt5.QtQml', 'PyQt5.QtQuickWidgets',
        'PyQt5.QtQuick3D', 'PyQt5.QtQuickControls2',
        'PyQt5.QtDesigner',
        'PyQt5.QtMultimedia', 'PyQt5.QtMultimediaWidgets',
        'PyQt5.QtLocation', 'PyQt5.QtPositioning',
        'PyQt5.QtNetwork', 'PyQt5.QtNetworkAuth', 'PyQt5.QtSql',
        'PyQt5.Qt3DCore', 'PyQt5.Qt3DRender', 'PyQt5.Qt3DInput',
        'PyQt5.Qt3DLogic', 'PyQt5.Qt3DAnimation', 'PyQt5.Qt3DExtras',
        'PyQt5.QtBluetooth', 'PyQt5.QtXmlPatterns',
        'PySide2', 'PySide6', 'PyQt6',
        'torch', 'torchvision', 'torchaudio',
        'cv2', 'scipy', 'numba', 'llvmlite',
        'tensorflow', 'keras', 'sklearn', 'lightgbm', 'xgboost', 'catboost',
        'ultralytics', 'IPython', 'jupyter',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
"""

_SPEC_ONEFILE = r"""
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

_SPEC_ONEDIR = r"""
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
    icon = find_icon()
    icon_line = f"icon={repr(str(icon))}," if icon else "# icon=None"
    spec_dir = HERE / "build"
    version_file = write_windows_version_info(
        spec_dir,
        internal_name=APP_NAME,
        original_filename=f"{APP_NAME}{_EXE_EXT}",
        file_description="FORECAST-SW Equation Library Manager",
    )
    version_line = f"version={repr(str(version_file))}," if version_file else "# version=None"

    datas = collect_bundled_datas()
    print(f"[bundle] {len(datas)} source files bundled (carbon_calculator + main.py + build_exe.py, ...)")

    analysis = (
        _SPEC_ANALYSIS
        .replace("__ENTRY__", repr(str(ENTRY)))
        .replace("__HERE__",  repr(str(HERE)))
        .replace("__DATAS__", repr(datas))
    )

    exe_tmpl = _SPEC_ONEDIR if onedir else _SPEC_ONEFILE
    exe_section = (
        exe_tmpl
        .replace("__APP_NAME__",  repr(APP_NAME))
        .replace("__CONSOLE__",   "True" if debug else "False")
        .replace("__UPX__",       "True" if upx else "False")
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
    print("Starting PyInstaller build (Equation Library Manager)")
    print(f"  entry point: {ENTRY}")
    print(f"  spec:      {spec_path}")
    print(f"  app name:    {APP_NAME}")
    print(f"  build env:   {build_venv}")
    print(f"  mode:        {'onedir' if args.onedir else 'onefile'}")
    print(f"  console:     {'shown' if args.debug else 'hidden (GUI)'}")
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
        print("=" * 70)
        return 1

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
        print()
        print("  -- How to distribute ------------------------------------------")
        print(f"  {out.name} next to build_exe.py in the source folder.")
        print("  Users can then double-click this executable to load a JSON and rebuild.")
        print("  ────────────────────────────────────────────────────────────")
    else:
        print(f"[failed] Build output not found: {out}")
    print("=" * 70)

    return 0 if out.exists() else 1


if __name__ == "__main__":
    sys.exit(main())
