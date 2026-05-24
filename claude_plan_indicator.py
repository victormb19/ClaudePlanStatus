#!/usr/bin/env python3
"""ClaudePlanStatus — indicador GNOME del uso del plan de Claude Code.

Lee ccusage (binario nativo) y muestra en la barra superior:
  - % de la ventana rodante de 5h
  - % del cap semanal configurable
Click para ver detalles, refrescar o editar config.
"""

import json
import shutil
import subprocess
import sys
import tomllib
from datetime import datetime, timedelta, timezone
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("AyatanaAppIndicator3", "0.1")
from gi.repository import GLib, Gtk, AyatanaAppIndicator3 as AppIndicator  # noqa: E402

PROJECT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = PROJECT_DIR / "config.toml"
ICON_PATH = PROJECT_DIR / "icon.svg"
CCUSAGE = shutil.which("ccusage") or str(Path.home() / ".local/bin/ccusage")

DEFAULT_CONFIG = {
    "limits": {"threshold_5h": "auto", "threshold_weekly": 5_000_000},
    "ui": {"poll_seconds": 30, "show_cost": True},
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


def run_ccusage(args):
    result = subprocess.run(
        [CCUSAGE, *args], capture_output=True, text=True, timeout=10
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "ccusage falló")
    return json.loads(result.stdout)


def fetch_active_block():
    blocks = run_ccusage(["blocks", "--active", "--json", "--offline"]).get("blocks") or []
    return blocks[0] if blocks else None


def fetch_weekly_current():
    data = run_ccusage(["weekly", "--json", "--offline"])
    weeks = data.get("weekly") or []
    if not weeks:
        return {"totalTokens": 0, "totalCost": 0.0}
    today = datetime.now(timezone.utc).date()
    monday = (today - timedelta(days=today.weekday())).isoformat()
    for w in weeks:
        if w.get("period") == monday:
            return w
    weeks.sort(key=lambda x: x.get("period", ""), reverse=True)
    return weeks[0]


def fetch_threshold_5h_auto():
    blocks = run_ccusage(["blocks", "--json", "--offline"]).get("blocks") or []
    historical = [b.get("totalTokens") or 0 for b in blocks if not b.get("isGap") and not b.get("isActive")]
    return max(historical) if historical else 1_000_000


def fmt_tokens(n):
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.0f}k"
    return str(n)


def fmt_remaining(end_iso):
    try:
        end = datetime.fromisoformat(end_iso.replace("Z", "+00:00"))
    except ValueError:
        return "—"
    delta = end - datetime.now(timezone.utc)
    if delta.total_seconds() <= 0:
        return "expirado"
    mins = int(delta.total_seconds() // 60)
    h, m = divmod(mins, 60)
    return f"{h}h {m}m" if h else f"{m}m"


def emoji_for_pct(pct):
    if pct >= 90:
        return "🔴"
    if pct >= 70:
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
        interval = max(5, int(self.config["ui"].get("poll_seconds", 30)))
        GLib.timeout_add_seconds(interval, self.poll)

    def _build_menu(self):
        self.menu = Gtk.Menu()
        self.item_5h = Gtk.MenuItem(label="5h: cargando…")
        self.item_weekly = Gtk.MenuItem(label="Semanal: cargando…")
        self.item_cost = Gtk.MenuItem(label="Coste: —")
        self.item_updated = Gtk.MenuItem(label="Actualizado: —")
        for item in (self.item_5h, self.item_weekly, self.item_cost, self.item_updated):
            item.set_sensitive(False)
            self.menu.append(item)
        self.menu.append(Gtk.SeparatorMenuItem())
        for label, handler in (
            ("Refrescar ahora", lambda _: self.poll()),
            ("Editar config…", self._open_config),
            ("Salir", lambda _: Gtk.main_quit()),
        ):
            item = Gtk.MenuItem(label=label)
            item.connect("activate", handler)
            self.menu.append(item)
        self.menu.show_all()
        self.indicator.set_menu(self.menu)

    def _open_config(self, _item):
        if not CONFIG_PATH.exists():
            CONFIG_PATH.write_text(
                '[limits]\nthreshold_5h = "auto"\nthreshold_weekly = 5000000\n\n'
                "[ui]\npoll_seconds = 30\nshow_cost = true\n"
            )
        subprocess.Popen(["xdg-open", str(CONFIG_PATH)])

    def poll(self):
        try:
            self.config = load_config()
            block = fetch_active_block()
            weekly = fetch_weekly_current()
            cfg = self.config["limits"]
            t5 = cfg.get("threshold_5h", "auto")
            if isinstance(t5, str) and t5.lower() == "auto":
                t5 = fetch_threshold_5h_auto()
            tw = int(cfg.get("threshold_weekly", 5_000_000))
            self._render(block, weekly, int(t5), tw)
        except Exception as e:
            self.indicator.set_label("⚠ Claude", "")
            self.item_5h.set_label(f"Error: {e}")
            self.item_weekly.set_label("")
            self.item_cost.set_label("")
            self.item_updated.set_label(f"Intento: {datetime.now().strftime('%H:%M:%S')}")
        return True

    def _render(self, block, weekly, t5, tw):
        if block:
            tk5 = block.get("totalTokens", 0)
            remaining = fmt_remaining(block.get("endTime", ""))
            cost = block.get("costUSD", 0.0)
        else:
            tk5, remaining, cost = 0, "sin bloque activo", 0.0
        pct5 = (tk5 / t5 * 100) if t5 else 0

        tkw = weekly.get("totalTokens", 0)
        costw = weekly.get("totalCost", 0.0)
        pctw = (tkw / tw * 100) if tw else 0

        emoji = emoji_for_pct(max(pct5, pctw))
        self.indicator.set_label(f"{emoji} 5h {pct5:.0f}% · 7d {pctw:.0f}%", "")
        self.item_5h.set_label(
            f"Bloque 5h: {fmt_tokens(tk5)} tokens ({pct5:.0f}%) · queda {remaining}"
        )
        self.item_weekly.set_label(
            f"Semanal: {fmt_tokens(tkw)} tokens ({pctw:.0f}%)"
        )
        if self.config["ui"].get("show_cost", True):
            self.item_cost.set_label(
                f"Coste: ${cost:.2f} bloque · ${costw:.2f} semana"
            )
            self.item_cost.show()
        else:
            self.item_cost.hide()
        self.item_updated.set_label(
            f"Actualizado: {datetime.now().strftime('%H:%M:%S')}"
        )


def main():
    if not Path(CCUSAGE).exists():
        print(f"ccusage no encontrado en {CCUSAGE}. Ejecuta install.sh.", file=sys.stderr)
        sys.exit(1)
    Indicator()
    Gtk.main()


if __name__ == "__main__":
    main()
