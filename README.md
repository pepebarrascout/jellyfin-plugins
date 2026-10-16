# jellyfin-plugins

Repositorio único que reúne todos mis plugins de Jellyfin en un solo
`manifest.json` y proporciona una landing page para instalarlos.

## Qué contiene este repositorio

```
jellyfin-plugins/
├── manifest.json              # Manifest combinado (Jellyfin lo consume)
├── index.html                 # Landing page estática
├── update-manifest.sh        # Script para regenerar a mano
├── scripts/
│   └── build_manifest.py      # Genera manifest.json e index.html
├── .github/workflows/
│   └── update-manifest.yml    # Auto-update diario vía GitHub Actions
├── README.md
└── .nojekyll                  # Desactiva Jekyll en GitHub Pages
```

Los manifest individuales de cada plugin **siguen en sus propios repos**:

| Plugin | Repo |
|---|---|
| Estadísticas | [jellyfin-plugin-estadisticas](https://github.com/pepebarrascout/jellyfin-plugin-estadisticas) |
| Last.fm | [jellyfin-plugin-lastfm](https://github.com/pepebarrascout/jellyfin-plugin-lastfm) |
| ListenBrainz | [jellyfin-plugin-listenbrainz](https://github.com/pepebarrascout/jellyfin-plugin-listenbrainz) |
| Podcasts | [jellyfin-plugin-podcast](https://github.com/pepebarrascout/jellyfin-plugin-podcast) |
| Radio Online | [jellyfin-plugin-radio-online](https://github.com/pepebarrascout/jellyfin-plugin-radio-online) |
| YouTube | [jellyfin-plugin-youtube](https://github.com/pepebarrascout/jellyfin-plugin-youtube) |

Este repo **no** modifica los anteriores. Solo los lee y combina.

## Cómo usar el manifest en Jellyfin

1. En Jellyfin: **Panel de control → Plugins → Repositorios → +**.
2. Pon el nombre que quieras (por ejemplo *pepebarrascout plugins*).
3. Pega la URL del manifest. Las dos opciones soportadas:
   - GitHub Pages: `https://pepebarrascout.github.io/jellyfin-plugins/manifest.json`
   - Tu propio servidor: `https://tu-dominio.com/ruta/jellyfin-plugins/manifest.json`
4. Guarda. Los plugins aparecerán en el catálogo filtrados por la versión
   de Jellyfin que tengas instalada (10.11 o 12.x) gracias al campo
   `targetAbi` de cada versión.

## Hosting (GitHub Pages + tu propio servidor)

### GitHub Pages (recomendado y ya configurado)

El repositorio está configurado para servir el contenido de la rama `main`
directamente en GitHub Pages. No requiere build ni Jekyll — usamos
`.nojekyll` para servir los archivos crudos.

- Landing: <https://pepebarrascout.github.io/jellyfin-plugins/>
- Manifest: <https://pepebarrascout.github.io/jellyfin-plugins/manifest.json>

Si el dominio `pepebarrascout.github.io` no funciona, verifica en
**Settings → Pages** del repo que la source está en `main` / root.

### Tu propio servidor

La landing es HTML+CSS+JS estático, sin backend. Cualquier servidor
sirve. Dos opciones comunes:

#### Nginx

```nginx
server {
  listen 80;
  server_name plugins.tu-dominio.com;
  root /var/www/jellyfin-plugins;
  index index.html;

  # Para que Jellyfin pueda leer el manifest, CORS no es necesario
  # porque Jellyfin descarga el JSON por HTTP sin restricciones de origen.
  location / {
    try_files $uri $uri/ =404;
  }

  # Content-type correcto para .json (algunos servidores lo sirven
  # como text/plain, lo que a Jellyfin no le gusta)
  location ~ \.json$ {
    add_header Content-Type application/json;
  }
}
```

Pasos para deployar:

```bash
# En tu servidor:
cd /var/www
git clone https://github.com/pepebarrascout/jellyfin-plugins.git
sudo ln -s /var/www/jellyfin-plugins /var/www/jellyfin-plugins  # si no lo clonaste ahí
sudo nginx -s reload
```

Para actualizar:

```bash
cd /var/www/jellyfin-plugins
git pull
# Si tienes python3 instalado y prefieres regenerar localmente:
./update-manifest.sh
# o solo:
git pull   # GitHub Actions ya habrá actualizado manifest.json e index.html
```

#### Apache

```apache
<VirtualHost *:80>
  ServerName plugins.tu-dominio.com
  DocumentRoot /var/www/jellyfin-plugins
  <Directory /var/www/jellyfin-plugins>
    Options Indexes FollowSymLinks
    AllowOverride None
    Require all granted
    AddType application/json .json
  </Directory>
</VirtualHost>
```

### Ventajas de GitHub Pages

- **Cero configuración**: el workflow ya hace commit y push automáticamente.
- **HTTPS gratis**: GitHub provee certificado válido para `*.github.io`.
- **CDN global**: sirve desde cualquier parte del mundo rápido.
- **Confiabilidad**: 99.9% uptime sin que tengas que mantener nada.

### Ventajas de tu propio servidor

- **Tu dominio**: puedes usar `plugins.tudominio.com` en lugar de la URL
  de GitHub.
- **Control total**: si quieres customizar la landing, no dependes del
  workflow de Pages.
- **Sin límites**: GitHub Pages tiene soft-limit de 100GB/mes de ancho
  de banda; tu servidor no.

### Recomendación

Mantén GitHub Pages activado como fuente principal. Es la opción más
simple y la URL queda pública sin mover un dedo. Si después quieres
tu propio dominio, puedes configurar un CNAME en tu DNS apuntando a
`pepebarrascout.github.io` (o usar el CNAME file en este repo).

## Actualización automática del manifest

Hay **dos mecanismos** que ya están configurados en este repo:

### 1. GitHub Actions (automático, sin intervención)

El workflow en `.github/workflows/update-manifest.yml` se ejecuta:

- Todos los días a las 00:00 UTC (cron).
- Manualmente desde la pestaña **Actions** → **Actualizar manifest combinado**
  → botón **Run workflow**.
- Tras cualquier push a `main` que toque `build_manifest.py` o el workflow.

El workflow:
1. Lee los 6 manifest.json de cada plugin desde la rama `main`.
2. Los combina en un único `manifest.json` (sin filtrar por `targetAbi`;
   Jellyfin filtra solo según la versión del servidor).
3. Regenera `index.html` con los datos actualizados.
4. Hace commit + push si hubo cambios.

No requiere configuración adicional. El token por defecto de GitHub
Actions (`GITHUB_TOKEN`) tiene permisos de escritura sobre el repo
(configurado en `permissions: contents: write` del workflow).

### 2. Script shell (manual, para emergencias o testing)

```bash
# Sin token (funciona para repos públicos; 60 req/hora por IP)
./update-manifest.sh

# Con token (recomendado, 5000 req/hora)
GITHUB_TOKEN=ghp_xxx ./update-manifest.sh

# Con commit + push automático si hubo cambios
./update-manifest.sh --commit
```

El script usa el mismo `build_manifest.py` que el workflow, así que el
output es idéntico. Útil para:

- Probar cambios en `build_manifest.py` antes de hacer push.
- Forzar una actualización inmediata sin esperar al cron diario.
- Regenerar el manifest en tu servidor propio tras un `git pull`.

### Agregar o quitar plugins

Edita la lista `PLUGINS` al principio de `scripts/build_manifest.py`:

```python
PLUGINS = [
    {"repo": "jellyfin-plugin-estadisticas", "github_url": "..."},
    # ... añade aquí un nuevo plugin
]
```

Después ejecuta `./update-manifest.sh --commit` (o espera al cron diario).

## Estructura del manifest combinado

`manifest.json` es un array JSON con un objeto por plugin. Cada objeto tiene
la misma estructura que el manifest individual de cada plugin, con
`versions` ordenadas por `timestamp` descendente (más nueva primero).

```json
[
  {
    "guid": "8a7b6c5d-4e3f-4a2b-9c1d-0e1f2a3b4c5d",
    "name": "Estadisticas",
    "description": "...",
    "overview": "...",
    "owner": "pepebarrascout",
    "category": "Music",
    "imageUrl": "https://raw.githubusercontent.com/.../logo.png",
    "versions": [
      {
        "version": "0.0.0.19",
        "changelog": "...",
        "targetAbi": "10.11.0.0",
        "sourceUrl": "https://github.com/.../releases/download/v0.0.0.19/...zip",
        "checksum": "E981DF898B673FE67E66918AA757E264",
        "timestamp": "2026-09-27T02:30:00Z"
      }
    ]
  }
]
```

Jellyfin decide qué versiones instalar en función del `targetAbi` de
cada versión comparado con la versión de Jellyfin Server. Las versiones
que no matcheen simplemente no aparecen en el catálogo.

## Licencia

El código de este repo (script, workflow, HTML, CSS) se publica bajo MIT.

Los plugins mismos conservan sus propias licencias en sus respectivos
repositorios.

## Contacto

Issues y pull requests en
[github.com/pepebarrascout/jellyfin-plugins](https://github.com/pepebarrascout/jellyfin-plugins).
