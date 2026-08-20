#!/usr/bin/env python3
"""ClaudePlanStatus — indicador GNOME del uso del plan de Claude Code.

Lee directamente el endpoint OAuth de Anthropic (api.anthropic.com/api/oauth/usage)
con el token guardado por el CLI de Claude Code en ~/.claude/.credentials.json.
Muestra los mismos % que ves en /usage o en tu pestaña de uso del perfil.
"""

import json
import os
import shutil
import ssl
import subprocess
import sys
import time
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
CREDS_BACKUP_PATH = CREDS_PATH.with_name(CREDS_PATH.name + ".bak")
CACHE_DIR = Path(
    os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")
) / "claude-plan-status"
CACHE_PATH = CACHE_DIR / "last_usage.json"

USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
TOKEN_URL = "https://console.anthropic.com/v1/oauth/token"
CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
OAUTH_BETA_HEADER = "oauth-2025-04-20"
USER_AGENT = "ClaudePlanStatus/1.0"

DEFAULT_CONFIG = {
    "ui": {
        "poll_seconds": 60,
        "warn_pct": 70,
        "alert_pct": 90,
        "show_extras": True,
        "stale_marker": "*",
        "stale_max_age_hours": 0,
        "auto_refresh_token": True,
        "refresh_margin_seconds": 300,
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


def read_credentials():
    with open(CREDS_PATH) as f:
        return json.load(f)


def read_access_token():
    return read_credentials()["claudeAiOauth"]["accessToken"]


def token_expires_within(creds, margin_seconds):
    """True si el accessToken caduca dentro del margen (expiresAt viene en ms)."""
    expires_at = (creds.get("claudeAiOauth") or {}).get("expiresAt")
    if not isinstance(expires_at, (int, float)):
        return False
    return time.time() * 1000 >= expires_at - margin_seconds * 1000


def save_credentials(creds):
    """Reescribe .credentials.json de forma atómica, con backup y modo 0600.

    El CLI de Claude Code lee este mismo archivo, así que se preserva cualquier
    clave que no sea del bloque OAuth y se deja una copia previa en .bak por si
    la rotación del refresh token dejase el archivo inservible.
    """
    shutil.copy2(CREDS_PATH, CREDS_BACKUP_PATH)
    tmp = CREDS_PATH.with_name(CREDS_PATH.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(creds, f)
    os.replace(tmp, CREDS_PATH)


def refresh_access_token():
    """Canjea el refreshToken por un accessToken nuevo y lo guarda.

    Devuelve el access token nuevo. Anthropic puede rotar también el refresh
    token, por eso hay que persistir la respuesta completa: si sólo lo
    guardásemos en memoria, el CLI se quedaría con un refresh token ya gastado.
    """
    creds = read_credentials()
    block = creds.get("claudeAiOauth") or {}
    refresh_token = block.get("refreshToken")
    if not refresh_token:
        raise RuntimeError("no hay refreshToken en .credentials.json")

    payload = json.dumps(
        {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": CLIENT_ID,
        }
    ).encode()
    req = urllib.request.Request(
        TOKEN_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
    )
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
        tok = json.loads(resp.read().decode())

    access_token = tok.get("access_token")
    if not access_token:
        raise RuntimeError("respuesta de refresh sin access_token")

    block["accessToken"] = access_token
    if tok.get("refresh_token"):
        block["refreshToken"] = tok["refresh_token"]
    if tok.get("expires_in"):
        block["expiresAt"] = int((time.time() + float(tok["expires_in"])) * 1000)
    creds["claudeAiOauth"] = block
    save_credentials(creds)
    return access_token


def _request_usage(token):
    req = urllib.request.Request(
        USAGE_URL,
        headers={
            "Authorization": f"Bearer {token}",
            "anthropic-beta": OAUTH_BETA_HEADER,
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
    )
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
        return json.loads(resp.read().decode())


def fetch_usage(auto_refresh=True, refresh_margin=300):
    creds = read_credentials()
    token = (creds.get("claudeAiOauth") or {}).get("accessToken")
    if auto_refresh and (not token or token_expires_within(creds, refresh_margin)):
        return _request_usage(refresh_access_token())
    if not token:
        raise RuntimeError("no hay accessToken en .credentials.json")
    try:
        return _request_usage(token)
    except urllib.error.HTTPError as e:
        if e.code != 401 or not auto_refresh:
            raise
        return _request_usage(refresh_access_token())


def save_cache(data):
    """Guarda el último uso conocido para poder seguir mostrándolo si falla la API."""
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = CACHE_PATH.with_suffix(".tmp")
        with open(tmp, "w") as f:
            json.dump({"ts": time.time(), "data": data}, f)
        tmp.replace(CACHE_PATH)
    except OSError:
        pass


def load_cache():
    try:
        with open(CACHE_PATH) as f:
            cached = json.load(f)
        if isinstance(cached.get("data"), dict):
            return float(cached.get("ts", 0)), cached["data"]
    except (OSError, ValueError, TypeError):
        pass
    return None


def fmt_age(ts):
    """Devuelve "hace 12m" para un epoch pasado."""
    secs = max(0, int(time.time() - ts))
    mins = secs // 60
    if mins < 1:
        return "hace segundos"
    if mins < 60:
        return f"hace {mins}m"
    h, m = divmod(mins, 60)
    if h < 24:
        return f"hace {h}h {m}m"
    d, h = divmod(h, 24)
    return f"hace {d}d {h}h"


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
        cached = load_cache()
        if cached is not None:
            self._render(cached[1], stale=(cached[0], "cargando…"))
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
            ("Renovar token ahora", self._force_refresh_token),
            ("Editar config…", self._open_config),
            ("Abrir uso en claude.ai", self._open_web_usage),
            ("Salir", lambda _: Gtk.main_quit()),
        ):
            item = Gtk.MenuItem(label=label)
            item.connect("activate", handler)
            self.menu.append(item)
        self.menu.show_all()
        self.indicator.set_menu(self.menu)

    def _force_refresh_token(self, _item):
        try:
            refresh_access_token()
        except Exception as e:  # noqa: BLE001
            self._error(f"refresh falló: {str(e)[:40]}")
            return
        self.poll()

    def _open_config(self, _item):
        subprocess.Popen(["xdg-open", str(CONFIG_PATH)])

    def _open_web_usage(self, _item):
        subprocess.Popen(["xdg-open", "https://claude.ai/settings/usage"])

    def poll(self):
        try:
            self.config = load_config()
            ui = self.config["ui"]
            data = fetch_usage(
                auto_refresh=bool(ui.get("auto_refresh_token", True)),
                refresh_margin=float(ui.get("refresh_margin_seconds", 300)),
            )
            save_cache(data)
            self._render(data)
        except urllib.error.HTTPError as e:
            if e.code in (400, 401, 403) and "oauth/token" in (e.url or ""):
                self._error("refresh rechazado — abre `claude` 1 vez")
            elif e.code == 401:
                self._error("token expirado — abre `claude` 1 vez")
            else:
                self._error(f"HTTP {e.code}")
        except FileNotFoundError:
            self._error(f"falta {CREDS_PATH}")
        except Exception as e:  # noqa: BLE001
            self._error(str(e)[:60])
        return True

    def _error(self, msg):
        """Sigue mostrando el último % conocido; sólo marca que está obsoleto."""
        cached = load_cache()
        if cached is not None:
            ts, data = cached
            max_age = float(self.config["ui"].get("stale_max_age_hours", 0) or 0)
            if max_age <= 0 or (time.time() - ts) <= max_age * 3600:
                self._render(data, stale=(ts, msg))
                return
        self.indicator.set_label("⚠ Claude", "")
        self.item_5h.set_label(f"Error: {msg}")
        self.item_5h_reset.set_label("")
        self.item_weekly.set_label("")
        self.item_weekly_reset.set_label("")
        self.item_extras.set_label("")
        self.item_updated.set_label(
            f"Intento: {datetime.now().strftime('%H:%M:%S')}"
        )

    @staticmethod
    def _extras(data):
        """[(etiqueta, %)] de los caps extra que el plan tenga activos."""
        out = []
        extra = data.get("extra_usage") or {}
        if extra.get("is_enabled") and extra.get("utilization") is not None:
            out.append(("Extra", float(extra["utilization"])))
        for key, label in (
            ("seven_day_opus", "Opus 7d"),
            ("seven_day_sonnet", "Sonnet 7d"),
        ):
            sub = data.get(key) or {}
            p = sub.get("utilization") if isinstance(sub, dict) else None
            if p is not None:
                out.append((label, float(p)))
        return out

    def _render(self, data, stale=None):
        ui = self.config["ui"]
        warn = float(ui.get("warn_pct", 70))
        alert = float(ui.get("alert_pct", 90))

        five = data.get("five_hour") or {}
        seven = data.get("seven_day") or {}
        pct5 = five.get("utilization")
        pct7 = seven.get("utilization")

        extras = self._extras(data) if ui.get("show_extras", True) else []

        pcts = [p for p in (pct5, pct7) if p is not None]
        pcts += [p for _, p in extras]
        worst = max(pcts) if pcts else None
        marker = str(ui.get("stale_marker", "*")) if stale else ""

        parts = []
        if pct5 is not None:
            parts.append(f"5h {pct5:.0f}%")
        if pct7 is not None:
            parts.append(f"7d {pct7:.0f}%")
        parts += [f"{label} {p:.0f}%" for label, p in extras]
        self.indicator.set_label(
            f"{emoji_for_pct(worst, warn, alert)} "
            + (" · ".join(parts) if parts else "Claude")
            + marker,
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

        if extras:
            self.item_extras.set_label(
                " · ".join(f"{label}: {p:.1f}%" for label, p in extras)
            )
            self.item_extras.set_visible(True)
        else:
            self.item_extras.set_label("")
            self.item_extras.set_visible(False)

        if stale:
            ts, msg = stale
            self.item_updated.set_label(
                f"Datos de {datetime.fromtimestamp(ts).strftime('%H:%M:%S')} "
                f"({fmt_age(ts)}) — {msg}"
            )
        else:
            self.item_updated.set_label(
                f"Actualizado: {datetime.now().strftime('%H:%M:%S')}"
            )


def main():
    if not CREDS_PATH.exists():
        print(
            f"No encuentro {CREDS_PATH}. ¿Tienes Claude Code logueado? "
            "Sigo mostrando el último uso cacheado.",
            file=sys.stderr,
        )
    Indicator()
    Gtk.main()


if __name__ == "__main__":
    main()
