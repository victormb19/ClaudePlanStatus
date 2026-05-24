#!/usr/bin/env python3
"""ClaudePlanStatus — indicador GNOME del uso del plan de Claude Code.

Lee directamente el endpoint OAuth de Anthropic (api.anthropic.com/api/oauth/usage)
con el token guardado por el CLI de Claude Code en ~/.claude/.credentials.json.
Muestra los mismos % que ves en /usage o en tu pestaña de uso del perfil.
"""

import json
import ssl
import subprocess
import sys
import tomllib
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("AyatanaAppIndicator3", "0.1")
from gi.repository import GLib, Gtk, AyatanaAppIndicator3 as AppIndicator  # noqa: E402

PROJECT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = PROJECT_DIR / "config.toml"
ICON_PATH = PROJECT_DIR / "icon.svg"
CREDS_PATH = Path.home() / ".claude" / ".credentials.json"

USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
OAUTH_BETA_HEADER = "oauth-2025-04-20"

DEFAULT_CONFIG = {
    "ui": {
        "poll_seconds": 60,
        "warn_pct": 70,
        "alert_pct": 90,
        "show_extras": True,
    },
}


def load_config():
    if not CONFIG_PATH.exists():
        return DEFAULT_CONFIG
    with open(CONFIG_PATH, "rb") as f:
        loaded = tomllib.load(f)
    cfg = {k: {**v} for k, v in DEFAULT_CONFIG.items()}
    for k, v in loaded.items():
        if isinstance(v, dict) and k in cfg:
            cfg[k].update(v)
        else:
            cfg[k] = v
    return cfg


def read_access_token():
    with open(CREDS_PATH) as f:
        return json.load(f)["claudeAiOauth"]["accessToken"]


def fetch_usage():
    token = read_access_token()
    req = urllib.request.Request(
        USAGE_URL,
        headers={
            "Authorization": f"Bearer {token}",
            "anthropic-beta": OAUTH_BETA_HEADER,
            "Accept": "application/json",
            "User-Agent": "ClaudePlanStatus/1.0",
        },
    )
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
        return json.loads(resp.read().decode())


def fmt_reset(iso_str):
    """Devuelve "queda 2h 15m" para timestamps futuros."""
    if not iso_str:
        return "—"
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
    except ValueError:
        return "—"
    delta = dt - datetime.now(timezone.utc)
    secs = int(delta.total_seconds())
    if secs <= 0:
        return "resetea ya"
    mins = secs // 60
    if mins < 60:
        return f"queda {mins}m"
    h, m = divmod(mins, 60)
    if h < 24:
        return f"queda {h}h {m}m"
    d, h = divmod(h, 24)
    return f"queda {d}d {h}h"


def emoji_for_pct(pct, warn, alert):
    if pct is None:
        return "❔"
    if pct >= alert:
        return "🔴"
    if pct >= warn:
        return "🟡"
    return "🟢"


class Indicator:
    def __init__(self):
        self.config = load_config()
        self.indicator = AppIndicator.Indicator.new(
            "claude-plan-status",
            str(ICON_PATH),
            AppIndicator.IndicatorCategory.APPLICATION_STATUS,
        )
        self.indicator.set_status(AppIndicator.IndicatorStatus.ACTIVE)
        self.indicator.set_title("Claude Plan Status")
        self._build_menu()
        self.indicator.set_label("⏳ Claude", "")
        self.poll()
        interval = max(15, int(self.config["ui"].get("poll_seconds", 60)))
        GLib.timeout_add_seconds(interval, self.poll)

    def _build_menu(self):
        self.menu = Gtk.Menu()
        self.item_5h = Gtk.MenuItem(label="5h: cargando…")
        self.item_5h_reset = Gtk.MenuItem(label="")
        self.item_weekly = Gtk.MenuItem(label="Semanal: cargando…")
        self.item_weekly_reset = Gtk.MenuItem(label="")
        self.item_extras = Gtk.MenuItem(label="")
        self.item_updated = Gtk.MenuItem(label="Actualizado: —")
        for item in (
            self.item_5h,
            self.item_5h_reset,
            self.item_weekly,
            self.item_weekly_reset,
            self.item_extras,
            self.item_updated,
        ):
            item.set_sensitive(False)
            self.menu.append(item)
        self.menu.append(Gtk.SeparatorMenuItem())
        for label, handler in (
            ("Refrescar ahora", lambda _: self.poll()),
            ("Editar config…", self._open_config),
            ("Abrir uso en claude.ai", self._open_web_usage),
            ("Salir", lambda _: Gtk.main_quit()),
        ):
            item = Gtk.MenuItem(label=label)
            item.connect("activate", handler)
            self.menu.append(item)
        self.menu.show_all()
        self.indicator.set_menu(self.menu)

    def _open_config(self, _item):
        subprocess.Popen(["xdg-open", str(CONFIG_PATH)])

    def _open_web_usage(self, _item):
        subprocess.Popen(["xdg-open", "https://claude.ai/settings/usage"])

    def poll(self):
        try:
            self.config = load_config()
            data = fetch_usage()
            self._render(data)
        except urllib.error.HTTPError as e:
            if e.code == 401:
                self._error("token expirado — abre `claude` 1 vez")
            else:
                self._error(f"HTTP {e.code}")
        except FileNotFoundError:
            self._error(f"falta {CREDS_PATH}")
        except Exception as e:  # noqa: BLE001
            self._error(str(e)[:60])
        return True

    def _error(self, msg):
        self.indicator.set_label("⚠ Claude", "")
        self.item_5h.set_label(f"Error: {msg}")
        self.item_5h_reset.set_label("")
        self.item_weekly.set_label("")
        self.item_weekly_reset.set_label("")
        self.item_extras.set_label("")
        self.item_updated.set_label(
            f"Intento: {datetime.now().strftime('%H:%M:%S')}"
        )

    def _render(self, data):
        ui = self.config["ui"]
        warn = float(ui.get("warn_pct", 70))
        alert = float(ui.get("alert_pct", 90))

        five = data.get("five_hour") or {}
        seven = data.get("seven_day") or {}
        pct5 = five.get("utilization")
        pct7 = seven.get("utilization")

        worst = max(p for p in (pct5, pct7) if p is not None) if (pct5 is not None or pct7 is not None) else None
        self.indicator.set_label(
            f"{emoji_for_pct(worst, warn, alert)} "
            f"5h {pct5:.0f}% · 7d {pct7:.0f}%"
            if pct5 is not None and pct7 is not None
            else f"{emoji_for_pct(worst, warn, alert)} Claude",
            "",
        )

        self.item_5h.set_label(
            f"Ventana 5h: {pct5:.1f}%" if pct5 is not None else "Ventana 5h: —"
        )
        self.item_5h_reset.set_label(
            f"   {fmt_reset(five.get('resets_at'))}" if five.get("resets_at") else ""
        )
        self.item_weekly.set_label(
            f"Semanal: {pct7:.1f}%" if pct7 is not None else "Semanal: —"
        )
        self.item_weekly_reset.set_label(
            f"   {fmt_reset(seven.get('resets_at'))}" if seven.get("resets_at") else ""
        )

        if ui.get("show_extras", True):
            extras = []
            extra = data.get("extra_usage") or {}
            if extra.get("is_enabled"):
                ext_pct = extra.get("utilization")
                if ext_pct is not None:
                    extras.append(f"Extra: {ext_pct:.0f}%")
            for key, label in (
                ("seven_day_opus", "Opus 7d"),
                ("seven_day_sonnet", "Sonnet 7d"),
            ):
                sub = data.get(key) or {}
                p = sub.get("utilization") if isinstance(sub, dict) else None
                if p is not None:
                    extras.append(f"{label}: {p:.0f}%")
            self.item_extras.set_label(" · ".join(extras) if extras else "")
            self.item_extras.set_visible(bool(extras))
        else:
            self.item_extras.hide()

        self.item_updated.set_label(
            f"Actualizado: {datetime.now().strftime('%H:%M:%S')}"
        )


def main():
    if not CREDS_PATH.exists():
        print(
            f"No encuentro {CREDS_PATH}. ¿Tienes Claude Code logueado?",
            file=sys.stderr,
        )
        sys.exit(1)
    Indicator()
    Gtk.main()


if __name__ == "__main__":
    main()
