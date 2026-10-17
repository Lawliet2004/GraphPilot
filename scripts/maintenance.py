"""Guards for offline native fault/restore drills, never an application API."""

import psutil


def assert_no_browser_tests(project):
    prefix = str(project / "node_modules") + "/"
    for process in psutil.process_iter(["cmdline"]):
        command = process.info["cmdline"] or []
        if "test" in command and any(
            arg.startswith(prefix) and "playwright" in arg for arg in command
        ):
            raise RuntimeError(
                "Run maintenance drills after browser tests finish; they share the development services"
            )
