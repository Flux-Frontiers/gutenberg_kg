"""Prove off-screen rendering works, without betting the session on it.

`dd898228` taught these suites to skip at *collection* when pyvista is absent,
because CI installs no optional extras and a collection error aborts the whole
run rather than skipping the affected files. That fixed the absent-pyvista
case. It does not cover the other one: pyvista **present** and unable to
render.

This VTK build has no OSMesa or EGL fallback, so constructing a ``Plotter``
without a working GL context does not raise -- it aborts the interpreter.
``importorskip`` cannot help, because the import succeeds; the crash comes
later, when a render window is created. Nor can ``try``/``except``: a fatal
abort is not an exception, and it takes the session down with every unrelated
test still queued behind it.

Running the render in a child process turns that crash into an exit code the
parent can read, at the cost of one subprocess.
"""

import subprocess
import sys
from functools import lru_cache

#: Executed in a child process, where a fatal abort is contained.
_PROBE_SOURCE = """
import pyvista as pv

plotter = pv.Plotter(off_screen=True, window_size=(32, 32))
plotter.add_mesh(pv.Sphere())
plotter.screenshot(None, return_img=True)
plotter.close()
"""

_PROBE_TIMEOUT = 120


@lru_cache(maxsize=1)
def can_render() -> bool:
    """Whether a minimal off-screen render completes in this environment.

    The result is cached, so the subprocess is spawned once per session no
    matter how many modules gate on it.

    :return: True if a child process completed the render cleanly.
    """
    try:
        proc = subprocess.run(
            [sys.executable, "-c", _PROBE_SOURCE],
            capture_output=True,
            timeout=_PROBE_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError):
        # No interpreter to spawn, or the probe hung past the timeout.
        return False
    # A fatal abort surfaces as a negative return code (-signal.SIGSEGV).
    return proc.returncode == 0
