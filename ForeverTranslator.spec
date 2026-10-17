from pathlib import Path

from PyInstaller.utils.hooks import collect_dynamic_libs


root = Path(SPEC).resolve().parent
datas = []
for source_root, destination_root in (
    (root / "models", "models"),
    (root / "addon" / "ForeverTranslatorProbe", "addon/ForeverTranslatorProbe"),
):
    for source in source_root.rglob("*"):
        if source.is_file():
            relative_parent = source.parent.relative_to(source_root)
            destination = Path(destination_root) / relative_parent
            datas.append((str(source), str(destination)))

analysis = Analysis(
    [str(root / "run_forever_translator.py")],
    pathex=[str(root / "app")],
    binaries=collect_dynamic_libs("ctranslate2"),
    datas=datas,
    hiddenimports=["ctranslate2", "sentencepiece"],
    noarchive=False,
)
pyz = PYZ(analysis.pure)
exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="ForeverTranslator",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)
collection = COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    name="ForeverTranslator",
)
