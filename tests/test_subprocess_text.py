"""Child-process output is read as UTF-8 so a non-ASCII byte does not kill the reader."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from frameforge.util.process_tree import text_output_kwargs


def test_undecodable_byte_does_not_crash_the_reader(tmp_path: Path):
    script = tmp_path / "emit.py"
    script.write_text("import sys\nsys.stdout.buffer.write(bytes([0x81, 0x0A]))\n", encoding="ascii")
    proc = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        check=False,
        **text_output_kwargs(),
    )
    assert proc.returncode == 0
    assert "\ufffd" in proc.stdout
