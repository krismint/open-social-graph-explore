from __future__ import annotations

import json
import os
import platform
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from core.db import PROJECT_ROOT


DEFAULT_CDP_PORT = int(os.environ.get("OSGE_CDP_PORT", "9222"))
DEFAULT_CACHE_ROOT = Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache")))
DEFAULT_CDP_PROFILE = Path(os.environ.get("OSGE_CDP_PROFILE", str(DEFAULT_CACHE_ROOT / "osge-chromium")))
DEFAULT_CDP_LOG = PROJECT_ROOT / "logs" / "chromium_cdp.log"
DEFAULT_CDP_START_URL = os.environ.get("OSGE_CDP_START_URL", "about:blank")


@dataclass(frozen=True)
class CdpStatus:
    ok: bool
    port: int
    url: str
    browser: str = ""
    websocket_debugger_url: str = ""
    profile_dir: str = ""
    started: bool = False
    error: str = ""


def cdp_version_url(port: int = DEFAULT_CDP_PORT) -> str:
    return f"http://127.0.0.1:{port}/json/version"


def probe_cdp(port: int = DEFAULT_CDP_PORT, profile_dir: Path | str = DEFAULT_CDP_PROFILE) -> CdpStatus:
    url = cdp_version_url(port)
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return CdpStatus(ok=False, port=port, url=url, profile_dir=str(profile_dir), error=str(exc))

    return CdpStatus(
        ok=True,
        port=port,
        url=url,
        browser=str(payload.get("Browser") or ""),
        websocket_debugger_url=str(payload.get("webSocketDebuggerUrl") or ""),
        profile_dir=str(profile_dir),
    )


def ensure_chromium_cdp(
    port: int = DEFAULT_CDP_PORT,
    profile_dir: Path | str = DEFAULT_CDP_PROFILE,
    log_path: Path | str = DEFAULT_CDP_LOG,
    headless: bool | None = None,
    timeout: int = 30,
) -> CdpStatus:
    current = probe_cdp(port, profile_dir)
    if current.ok:
        return current

    browser = detect_chromium_binary()
    if browser is None:
        return CdpStatus(
            ok=False,
            port=port,
            url=cdp_version_url(port),
            profile_dir=str(profile_dir),
            error="Cannot find a local Chrome/Chromium executable.",
        )

    profile = Path(profile_dir)
    profile.mkdir(parents=True, exist_ok=True)
    log = Path(log_path)
    log.parent.mkdir(parents=True, exist_ok=True)
    use_headless = _env_bool("OSGE_CDP_HEADLESS", False) if headless is None else headless

    args = [
        browser,
        f"--remote-debugging-port={port}",
        "--remote-debugging-address=127.0.0.1",
        f"--user-data-dir={profile}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-background-networking",
        "--disable-background-timer-throttling",
        "--disable-backgrounding-occluded-windows",
        "--disable-client-side-phishing-detection",
        "--disable-component-update",
        "--disable-default-apps",
        "--disable-domain-reliability",
        "--disable-extensions",
        "--disable-pings",
        "--disable-renderer-backgrounding",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--disable-sync",
        "--metrics-recording-only",
        "--disable-features=TranslateUI,MediaRouter,OptimizationHints,AutofillServerCommunication",
        "--disable-blink-features=AutomationControlled",
        "--exclude-switches=enable-automation",
    ]
    if use_headless:
        args.extend(["--headless=new", "--disable-gpu"])
    else:
        args.append("--start-maximized")
        if DEFAULT_CDP_START_URL:
            args.append(DEFAULT_CDP_START_URL)

    env = os.environ.copy()
    if platform.system() == "Linux" and not use_headless:
        env.setdefault("DISPLAY", ":0")

    with log.open("a", encoding="utf-8") as handle:
        handle.write(f"[OSGE] starting Chromium CDP: {' '.join(args)}\n")
        handle.flush()
        subprocess.Popen(
            args,
            stdout=handle,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
            env=env,
        )

    deadline = time.time() + timeout
    while time.time() < deadline:
        status = probe_cdp(port, profile)
        if status.ok:
            return CdpStatus(
                ok=True,
                port=status.port,
                url=status.url,
                browser=status.browser,
                websocket_debugger_url=status.websocket_debugger_url,
                profile_dir=status.profile_dir,
                started=True,
            )
        time.sleep(0.5)

    status = probe_cdp(port, profile)
    return CdpStatus(
        ok=False,
        port=port,
        url=cdp_version_url(port),
        profile_dir=str(profile),
        started=True,
        error=status.error or f"Chromium CDP did not become ready within {timeout}s.",
    )


def detect_chromium_binary() -> str | None:
    configured = os.environ.get("OSGE_CDP_BROWSER", "").strip()
    candidates = [configured] if configured else []
    system = platform.system()
    if system == "Darwin":
        candidates.extend(
            [
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                "/Applications/Chromium.app/Contents/MacOS/Chromium",
                "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            ]
        )
    elif system == "Windows":
        candidates.extend(
            [
                os.path.expandvars(r"%PROGRAMFILES%\Google\Chrome\Application\chrome.exe"),
                os.path.expandvars(r"%PROGRAMFILES(X86)%\Google\Chrome\Application\chrome.exe"),
                os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
                os.path.expandvars(r"%PROGRAMFILES%\Microsoft\Edge\Application\msedge.exe"),
            ]
        )
    else:
        candidates.extend(
            [
                "/usr/bin/chromium",
                "/usr/bin/chromium-browser",
                "/usr/bin/google-chrome",
                "/usr/bin/google-chrome-stable",
                "/snap/bin/chromium",
                "/usr/bin/microsoft-edge",
                "/usr/bin/microsoft-edge-stable",
            ]
        )

    for candidate in candidates:
        if candidate and Path(candidate).is_file() and os.access(candidate, os.X_OK):
            return candidate
    return None


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}
