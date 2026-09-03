from pathlib import Path
ROOT = Path(__file__).parents[1]


def test_windows_launcher_uses_managed_python() -> None:
    installer = (ROOT / "install" / "install.ps1").read_text()
    assert "`$env:CERES_PYTHON =" in installer
    assert "`$env:VIRTUAL_ENV =" in installer
    assert "-m ceres run all" in installer
    assert "$CeresExe" not in installer


def test_unix_launcher_uses_managed_python() -> None:
    installer = (ROOT / "install" / "install.sh").read_text()
    assert "export CERES_PYTHON=" in installer
    assert "export VIRTUAL_ENV=" in installer
    assert '"$PYTHON_BIN") -m ceres run all' in installer
