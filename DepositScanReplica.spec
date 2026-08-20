# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec: eseguibile Windows singolo, avvia la GUI.

Build (su Windows, vedi build_windows.bat):
    pyinstaller --clean --noconfirm DepositScanReplica.spec
Risultato: dist\\DepositScanReplica.exe
"""

block_cipher = None

a = Analysis(
    ['gui.py'],
    pathex=['src'],
    binaries=[],
    # i template dei caratteri servono a runtime: senza, niente lettura etichette
    datas=[('src/label_templates.npz', '.')],
    hiddenimports=[
        'pipeline', 'worker', 'geometry', 'card_mask', 'label_ocr',
        'label_glyphs', 'deposit_metrics',
        'openpyxl',
        'scipy._lib.array_api_compat.numpy.fft',
        'scipy.special._cdflib',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # roba pesante che non usiamo: tenerla fuori dimezza l'eseguibile
    excludes=['matplotlib', 'pytest', 'IPython', 'pandas', 'pytesseract'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='DepositScanReplica',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,      # applicazione a finestre: nessun terminale nero
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
