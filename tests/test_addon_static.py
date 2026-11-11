from pathlib import Path
import ast


def test_addon_sources_parse_without_blender():
    root=Path(__file__).parents[1]/'easykig'
    for file in root.glob('*.py'):
        ast.parse(file.read_text(encoding='utf-8'),filename=file.name)


def test_mmd_tools_not_vendored():
    root=Path(__file__).parents[1]
    assert not (root/'mmd_tools').exists()
    assert not (root/'easykig'/'mmd_tools').exists()
