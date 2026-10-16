#!/usr/bin/env python3
"""
build_manifest.py
=================

Genera dos archivos a partir de los manifest.json publicados en cada
repositorio de plugin de Jellyfin de pepebarrascout:

  1. manifest.json  — un único manifest que reúne TODOS los plugins
                       (todas sus versiones, sin filtrar por targetAbi;
                       Jellyfin filtra por targetAbi automáticamente al
                       mostrarlos en el catálogo).
  2. index.html     — landing page estática estilo k1k4k, en español.

Uso:
    python3 scripts/build_manifest.py \
        --output manifest.json --html index.html

No requiere autenticación si los repositorios de los plugins son públicos.
Si se pasa --token, se usa como Bearer para subir el rate-limit de la API
de GitHub (recomendado en el workflow de Actions).

El script es idempotente: si se ejecuta dos veces seguidas sin cambios en
los plugins fuente, produce exactamente el mismo output (orden determinista).
"""

from __future__ import annotations

import argparse
import datetime as _dt
import html
import json
import sys
import urllib.request
import urllib.error
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuración — editar solo aquí si se agregan o quitan plugins.
# El orden de esta lista determina el orden en que aparecen en la landing.
# ---------------------------------------------------------------------------
PLUGINS: list[dict] = [
    {
        "repo": "jellyfin-plugin-estadisticas",
        "github_url": "https://github.com/pepebarrascout/jellyfin-plugin-estadisticas",
        "display_title": "Estadísticas",
        "spanish_description": "Plugin de estadísticas de música para Jellyfin. Registra reproducciones de audio en una base de datos SQLite propia (sin tocar la BD de Jellyfin) y genera informes Top 50 y Bottom 50 por canción, artista, álbum y género en múltiples ventanas temporales. Permite crear listas de reproducción y programar su publicación.",
    },
    {
        "repo": "jellyfin-plugin-lastfm",
        "github_url": "https://github.com/pepebarrascout/jellyfin-plugin-lastfm",
        "display_title": "Last.fm",
        "spanish_description": "Scrobblea tu música a Last.fm, actualiza el estado de reproducción actual y marca tus canciones favoritas o rechazadas directamente desde Jellyfin.",
    },
    {
        "repo": "jellyfin-plugin-listenbrainz",
        "github_url": "https://github.com/pepebarrascout/jellyfin-plugin-listenbrainz",
        "display_title": "ListenBrainz",
        "spanish_description": "Scrobblea tu música a ListenBrainz desde Jellyfin. Actualiza el estado de ahora reproduciendo, envía scrobbles automáticamente y gestiona tus canciones favoritas (love/hate) con autenticación simple mediante token de usuario.",
    },
    {
        "repo": "jellyfin-plugin-podcast",
        "github_url": "https://github.com/pepebarrascout/jellyfin-plugin-podcast",
        "display_title": "Podcasts",
        "spanish_description": "Gestiona suscripciones a podcasts con actualizaciones automáticas del feed RSS, descarga automática de episodios, eliminación tras la escucha y generación diaria de listas de reproducción con episodios no escuchados.",
    },
    {
        "repo": "jellyfin-plugin-radio-online",
        "github_url": "https://github.com/pepebarrascout/jellyfin-plugin-radio-online",
        "display_title": "Radio Online",
        "spanish_description": "Plugin de streaming automatizado de radio en línea mediante Liquidsoap. Transmite audio a servidores Icecast con programación semanal de listas de reproducción a través del control por Telnet de Liquidsoap.",
    },
    {
        "repo": "jellyfin-plugin-youtube",
        "github_url": "https://github.com/pepebarrascout/jellyfin-plugin-youtube",
        "display_title": "YouTube",
        "spanish_description": "Reproduce videos de YouTube como Series en Jellyfin sin descargarlos. Usa archivos .strm + proxy local + yt-dlp. Sin necesidad de API key de YouTube.",
    },
]

OWNER = "pepebarrascout"
BRANCH = "main"
RAW_BASE = f"https://raw.githubusercontent.com/{OWNER}"


# ---------------------------------------------------------------------------
# Utilidades HTTP
# ---------------------------------------------------------------------------
def fetch(url: str, token: str | None) -> bytes:
    req = urllib.request.Request(url)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    req.add_header("User-Agent", "pepebarrascout-jellyfin-plugins-builder")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code} fetching {url}: {e.reason}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"URL error fetching {url}: {e.reason}") from e


def fetch_manifest(repo: str, token: str | None) -> list[dict]:
    """Devuelve el contenido del manifest.json del repo (lista de plugins)."""
    url = f"{RAW_BASE}/{repo}/{BRANCH}/manifest.json"
    data = fetch(url, token)
    try:
        parsed = json.loads(data.decode("utf-8"))
    except json.JSONDecodeError as e:
        raise RuntimeError(f"manifest.json de {repo} no es JSON válido: {e}") from e
    if not isinstance(parsed, list):
        # algunos manifests vienen como objeto único, normalizar
        if isinstance(parsed, dict):
            parsed = [parsed]
        else:
            raise RuntimeError(f"manifest.json de {repo} no es lista ni objeto")
    return parsed


# ---------------------------------------------------------------------------
# Lógica de combinación
# ---------------------------------------------------------------------------
def sort_versions_desc(versions: list[dict]) -> list[dict]:
    """Ordena versiones por timestamp desc (más nueva primero).
    Si no hay timestamp, ordena por version string desc como fallback.
    """
    def key(v: dict) -> tuple:
        ts = v.get("timestamp", "")
        # uso string ISO comparable; si falta, mandamos al final
        return (ts if isinstance(ts, str) else "", v.get("version", ""))
    return sorted(versions, key=key, reverse=True)


def build_combined_manifest(token: str | None) -> list[dict]:
    """Combina todos los manifest.json de cada plugin en un único array.
    El array resultante tiene un objeto por plugin (con sus versions ordenadas).
    """
    combined: list[dict] = []
    for p in PLUGINS:
        repo = p["repo"]
        try:
            plugin_list = fetch_manifest(repo, token)
        except RuntimeError as e:
            print(f"WARN: {e}", file=sys.stderr)
            continue
        if not plugin_list:
            print(f"WARN: {repo} devolvió manifest vacío", file=sys.stderr)
            continue
        # Tomamos el primer objeto del array (cada repo tiene 1 plugin)
        plugin_obj = dict(plugin_list[0])
        # Ordenamos versiones: más nueva primero
        plugin_obj["versions"] = sort_versions_desc(plugin_obj.get("versions", []))
        # Aseguramos campos críticos
        plugin_obj.setdefault("owner", OWNER)
        # github_url para el link del landing (no va en el manifest final,
        # pero lo guardamos temporalmente para el HTML)
        combined.append(plugin_obj)
    return combined


def strip_for_manifest(plugin_obj: dict) -> dict:
    """Quita cualquier campo extra que solo usamos internamente."""
    return {k: v for k, v in plugin_obj.items() if not k.startswith("_")}


# ---------------------------------------------------------------------------
# Generación del HTML (landing page)
# ---------------------------------------------------------------------------
CSS = """
:root {
  --bg: #0b0c0e;
  --card: #16181c;
  --text: #e8e8e8;
  --muted: #9aa0a6;
  --accent: #00a4dc;
  --accent2: #b900a4;
  --border: #2a2d33;
  --ok: #4caf50;
  --warn: #ffb300;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font: 16px/1.55 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
}
main { max-width: 880px; margin: 0 auto; padding: 48px 16px 64px; }
h1 { font-size: 1.9em; margin: 0 0 .2em; }
h1 span { color: var(--accent); }
h2 { font-size: 1.15em; margin: 2.2em 0 .8em; color: #fff; }
p { margin: .4em 0; }
.muted { color: var(--muted); }
.steps { color: var(--muted); font-size: .95em; }
.url {
  display: flex; align-items: center; gap: 12px;
  background: var(--card); border: 1px solid var(--border);
  border-radius: 8px; padding: 10px 12px; margin: 8px 0;
}
.url b { flex: 0 0 8em; font-weight: 600; }
.url code {
  flex: 1 1 auto; min-width: 0; overflow-wrap: anywhere;
  font: .9em ui-monospace, Consolas, monospace; color: #fff;
}
.url button {
  flex: 0 0 auto; background: var(--accent); color: #fff;
  border: 0; border-radius: 6px; padding: 6px 12px;
  font: inherit; font-size: .9em; cursor: pointer;
}
.url button:hover { filter: brightness(1.1); }
.plugin {
  display: flex; gap: 16px; align-items: center;
  background: var(--card); border: 1px solid var(--border);
  border-radius: 8px; padding: 12px; margin: 10px 0;
  text-decoration: none; color: inherit;
}
.plugin:hover { border-color: var(--accent); }
.plugin img {
  width: 160px; aspect-ratio: 16/9; border-radius: 6px;
  flex: 0 0 auto; background: #000; object-fit: cover;
}
.plugin h3 { margin: 0 0 .2em; font-size: 1.05em; color: #fff; }
.plugin p { color: var(--muted); font-size: .93em; margin: .2em 0; }
.plugin .badges { margin-top: .35em; display: flex; flex-wrap: wrap; gap: 6px; }
.badge {
  display: inline-block; padding: 2px 8px; border-radius: 10px;
  font-size: .75em; font-weight: 600; border: 1px solid var(--border);
  background: #000; color: var(--muted);
}
.badge.j12 { color: var(--accent); border-color: var(--accent); }
.badge.j10 { color: var(--warn); border-color: var(--warn); }
.badge.cat { color: #fff; background: #2a2d33; border-color: #2a2d33; }
.compat {
  margin: .35em 0;
  font-size: .85em;
  color: var(--muted);
}
.compat b { color: #fff; font-weight: 600; }
.versions {
  margin: 6px 0 0 0; padding: 0; list-style: none;
  font-size: .82em; color: var(--muted);
}
.versions li {
  padding: 4px 0; border-top: 1px dashed var(--border);
  display: flex; flex-wrap: wrap; gap: 8px; align-items: baseline;
}
.versions li:first-child { border-top: 0; }
.versions .ver { color: #fff; font-family: ui-monospace, Consolas, monospace; }
.versions .abi { color: var(--accent); font-size: .9em; }
.versions .date { color: var(--muted); font-size: .9em; }
.versions .cl { color: var(--muted); flex-basis: 100%; white-space: pre-wrap; }
footer { margin-top: 3em; color: var(--muted); font-size: .85em; }
a { color: var(--accent); }
.gh-link { font-size: .82em; color: var(--accent); margin-top: .25em; display: inline-block; }
@media (max-width: 560px) {
  .url { flex-wrap: wrap; }
  .url b { flex-basis: 100%; }
  .plugin { flex-direction: column; align-items: stretch; }
  .plugin img { width: 100%; }
}
"""


def _esc(s: str) -> str:
    return html.escape(s if s is not None else "")


def _fmt_date(ts: str) -> str:
    """Convierte 2026-09-27T02:30:00Z → 27-09-2026."""
    if not ts:
        return ""
    try:
        dt = _dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return ts
    return dt.strftime("%d-%m-%Y")


def _fmt_abi(abi: str) -> str:
    """Formatea targetAbi a algo legible.
    Ejemplos:
      "12.1.0.0"  -> "Jellyfin 12.1"
      "10.11.0.0" -> "Jellyfin 10.11"
      "10.11.8.0" -> "Jellyfin 10.11.8"
    """
    if not abi:
        return "Jellyfin"
    parts = abi.split(".")
    while parts and parts[-1] == "0":
        parts.pop()
    if not parts:
        return "Jellyfin"
    return "Jellyfin " + ".".join(parts)


def _category_badge(plugin_obj: dict) -> str:
    """Devuelve solo el badge de categoría (Music, Metadata, etc.)."""
    cat = plugin_obj.get("category", "")
    if not cat:
        return ""
    # Traducimos las categorías comunes al español
    cat_translations = {
        "Music": "Música",
        "Metadata": "Metadata",
        "General": "General",
        "Channels": "Canales",
        "Live TV": "TV en vivo",
    }
    cat_es = cat_translations.get(cat, cat)
    return f'<div class="badges"><span class="badge cat">{_esc(cat_es)}</span></div>'


def _compat_line(plugin_obj: dict) -> str:
    """Devuelve la línea 'Compatible con Jellyfin X.Y' basada en la última versión."""
    versions = plugin_obj.get("versions", [])
    if not versions:
        return ""
    latest = versions[0]
    abi = latest.get("targetAbi", "")
    if not abi:
        return ""
    return f'<div class="compat">Compatible con <b>{_esc(_fmt_abi(abi))}</b></div>'


def _versions_list(plugin_obj: dict, max_v: int = 1) -> str:
    """Lista las últimas N versiones (por defecto solo 1) con versión, targetAbi, fecha y changelog."""
    versions = plugin_obj.get("versions", [])[:max_v]
    if not versions:
        return ""
    items = []
    for v in versions:
        ver = v.get("version", "")
        abi = v.get("targetAbi", "")
        date = _fmt_date(v.get("timestamp", ""))
        cl = v.get("changelog", "").strip()
        # limitamos el changelog a 600 chars para que no se haga eterno
        if len(cl) > 600:
            cl = cl[:597] + "..."
        items.append(
            "<li>"
            f'<span class="ver">v{_esc(ver)}</span>'
            f'<span class="abi">targetAbi {_esc(abi)}</span>'
            f'<span class="date">{_esc(date)}</span>'
            f'<span class="cl">{_esc(cl)}</span>'
            "</li>"
        )
    total_versions = len(plugin_obj.get("versions", []))
    more_line = ""
    if total_versions > max_v:
        more_line = f'<li style="border-top:1px dashed var(--border);color:var(--muted);font-style:italic;">Hay {total_versions - max_v} versión(es) anterior(es) en el repositorio.</li>'
    return f'<ul class="versions">{"".join(items)}{more_line}</ul>'


def build_html(combined: list[dict], manifest_url: str) -> str:
    plugin_cards = []
    for p in combined:
        name = p.get("name", "")
        # intentamos resolver overrides (display_title, spanish_description)
        # buscando el plugin en PLUGINS por coincidencia con el repo
        repo_key = None
        for plugin_meta in PLUGINS:
            # heurística: el nombre del plugin debería ser subset del nombre del repo
            # o el repo debería contener el slug del nombre
            slug = name.lower().replace(" ", "-").replace(".", "")
            if slug in plugin_meta["repo"].lower() or plugin_meta["repo"].lower().endswith(slug):
                repo_key = plugin_meta["repo"]
                break
        if not repo_key:
            # fallback por orden
            idx = combined.index(p)
            if idx < len(PLUGINS):
                repo_key = PLUGINS[idx]["repo"]
        plugin_meta = next((x for x in PLUGINS if x["repo"] == repo_key), {})
        # Título: "Jellyfin Plugin <DisplayTitle>"
        display_title = plugin_meta.get("display_title", name)
        title = f"Jellyfin Plugin {display_title}"
        # Descripción: usamos la descripción en español del override si existe,
        # si no, usamos description/overview del manifest
        desc = plugin_meta.get("spanish_description") or p.get("description", "") or p.get("overview", "")
        image = p.get("imageUrl", "")
        gh_url = plugin_meta.get("github_url", f"https://github.com/{OWNER}/{repo_key or ''}")

        # Layout por card (en orden):
        #   1. Título (h3)
        #   2. Descripción (p)
        #   3. Compatible con Jellyfin X.Y
        #   4. Etiqueta de categoría (Música, Metadata, etc.)
        #   5. Enlace al repositorio en GitHub
        #   6. Únicamente la versión más reciente
        card = (
            '<a class="plugin" href="' + _esc(gh_url) + '">'
            f'<img src="{_esc(image)}" alt="" onerror="this.src=\'data:image/svg+xml;utf8,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 16 9%22><rect width=%2216%22 height=%229%22 fill=%22%230b0c0e%22/><text x=%228%22 y=%225%22 font-size=%221%22 fill=%22%239aa0a6%22 text-anchor=%22middle%22>sin logo</text></svg>\'; this.onerror=null;">'
            "<div>"
            f"<h3>{_esc(title)}</h3>"
            f"<p>{_esc(desc)}</p>"
            f"{_compat_line(p)}"
            f"{_category_badge(p)}"
            f'<span class="gh-link">{_esc(gh_url.replace("https://", ""))}</span>'
            f"{_versions_list(p, max_v=1)}"
            "</div>"
            "</a>"
        )
        plugin_cards.append(card)

    plugins_html = "\n".join(plugin_cards)

    return f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Pepe Barrascout · Plugins para Jellyfin</title>
<meta name="description" content="Repositorio único con todos los plugins de Jellyfin de Pepe Barrascout: Estadísticas, Last.fm, ListenBrainz, Podcasts, Radio Online y YouTube.">
<style>
{CSS}
</style>
</head>
<body>
<main>
  <h1>Pepe Barrascout <span>· Plugins para Jellyfin</span></h1>
  <p class="muted">Un único repositorio para todos mis plugins de Jellyfin. Añádelo una vez y cada plugin,
  con todas sus actualizaciones, aparecerá automáticamente en el catálogo de Jellyfin.</p>

  <h2>URL del repositorio</h2>
  <p class="steps">Panel → Plugins → Administrar repositorios → <b>+</b></p>
  <div class="url">
    <b>Manifest</b>
    <code id="umanifest">{_esc(manifest_url)}</code>
    <button type="button" data-copy="umanifest">Copiar</button>
  </div>
  <p class="muted" style="font-size:.85em;margin-top:.5em;">
    Esta URL es la misma página donde estás ahora, terminada en <code>/manifest.json</code>.
    Si la landing se sirve desde otro dominio (por ejemplo en tu propio servidor),
    el botón copiará la URL correspondiente a ese dominio automáticamente.
  </p>

  <h2>Plugins incluidos</h2>
  {plugins_html}

  <h2>Cómo instalar</h2>
  <ol class="steps">
    <li>En Jellyfin, ve a <b>Panel de control → Plugins → Repositorios</b>.</li>
    <li>Pulsa el botón <b>+</b> para añadir un nuevo repositorio.</li>
    <li>Asigna un nombre (por ejemplo <i>pepebarrascout plugins</i>) y pega la URL del manifest de arriba.</li>
    <li>Guarda. En el catálogo de plugins aparecerán todos mis plugins, con sus versiones compatibles
    según tu Jellyfin (10.11 o 12.x).</li>
    <li>Instala el que quieras. Las actualizaciones futuras llegarán solas a través del catálogo.</li>
  </ol>

  <h2>Compatibilidad</h2>
  <p class="muted">
    Cada plugin incluye versiones para Jellyfin 10.11.x y para Jellyfin 12.x cuando aplica.
    En el catálogo, Jellyfin solo muestra las versiones compatibles con tu servidor (según
    <code>targetAbi</code>). No tienes que hacer nada manual para filtrarlas.
  </p>
  <p class="muted">
    Los badges junto a cada plugin indican qué ramas de Jellyfin tiene versiones publicadas:
    <span class="badge j12">Jellyfin 12.x</span>
    <span class="badge j10">Jellyfin 10.11</span>
  </p>

  <h2>Repositorios en GitHub</h2>
  <p class="muted">Cada plugin mantiene su propio repositorio con su código fuente, sus releases y su manifest individual:</p>
  <ul class="steps">
""" + "\n".join(
    f'    <li><a href="{_esc(p["github_url"])}">{_esc(p["github_url"].replace("https://", ""))}</a></li>'
    for p in PLUGINS
) + f"""
  </ul>

  <footer>
    Fuente: <a href="https://github.com/{OWNER}/jellyfin-plugins">github.com/{OWNER}/jellyfin-plugins</a>
    · El manifest combinado se regenera automáticamente todos los días vía GitHub Actions.
    · Última actualización: {_fmt_date(_dt.datetime.now(_dt.timezone.utc).isoformat())}
  </footer>
</main>
<script>
  // Copiar al portapapeles
  document.querySelectorAll('[data-copy]').forEach(function (btn) {{
    btn.addEventListener('click', function () {{
      var text = document.getElementById(btn.getAttribute('data-copy')).textContent;
      var done = function () {{
        btn.textContent = 'Copiado ✓';
        setTimeout(function () {{ btn.textContent = 'Copiar'; }}, 1500);
      }};
      if (navigator.clipboard && navigator.clipboard.writeText) {{
        navigator.clipboard.writeText(text).then(done, function () {{}});
      }} else {{
        // fallback
        var ta = document.createElement('textarea');
        ta.value = text; document.body.appendChild(ta);
        ta.select(); try {{ document.execCommand('copy'); }} catch(e) {{}}
        document.body.removeChild(ta); done();
      }}
    }});
  }});
  // Calcular la URL del manifest relativa al dominio actual
  (function () {{
    var code = document.getElementById('umanifest');
    if (code) {{
      var base = window.location.href.replace(/index\\.html?$/, '').replace(/\\/$/, '');
      code.textContent = base + '/manifest.json';
    }}
  }})();
</script>
<script defer src="https://stats.blogsdeguatemala.com/script.js" data-website-id="b844201b-c1e8-4e88-9b67-20a6109583ce"></script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output", default="manifest.json",
                    help="Archivo de salida para el manifest combinado")
    ap.add_argument("--html", default="index.html",
                    help="Archivo de salida para la landing page HTML")
    ap.add_argument("--token", default=None,
                    help="GitHub token (opcional, sube rate-limit)")
    ap.add_argument("--manifest-url", default=None,
                    help="URL pública del manifest combinado. Si se omite, "
                         "se calcula a partir de --output.")
    args = ap.parse_args()

    print(f"Construyendo manifest combinado desde {len(PLUGINS)} plugins...",
          file=sys.stderr)
    combined = build_combined_manifest(args.token)
    if not combined:
        print("ERROR: no se pudo construir ningún plugin", file=sys.stderr)
        return 1

    # Escribir manifest.json (sin campos internos)
    cleaned = [strip_for_manifest(p) for p in combined]
    out_path = Path(args.output)
    out_path.write_text(
        json.dumps(cleaned, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8"
    )
    print(f"  manifest.json → {out_path} ({len(cleaned)} plugins)",
          file=sys.stderr)

    # Determinar URL pública del manifest para el HTML
    if args.manifest_url:
        manifest_url = args.manifest_url
    else:
        # valor por defecto para GitHub Pages; se ajusta en runtime vía JS
        manifest_url = f"https://{OWNER}.github.io/jellyfin-plugins/manifest.json"

    html_path = Path(args.html)
    html_path.write_text(build_html(combined, manifest_url), encoding="utf-8")
    print(f"  index.html    → {html_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
