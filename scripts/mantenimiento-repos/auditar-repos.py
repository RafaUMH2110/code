#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""auditar-repos.py — Revisa los repos de RafaUMH2110 sin modificar nada.

Autor: Rafa · Departamento de Ingeniería de Sistemas y Automática ·
Universidad Miguel Hernández de Elche · r.puerto@umh.es
Generado con IA · Revisado por el autor

Solo lee: ejecuta `git` sobre clones locales y, con --clonar, consulta la API
pública de GitHub y clona (en DIR) los repos públicos no archivados.
Solo biblioteca estándar de Python 3.7+ (PyYAML es opcional, para validar los
workflows).

Comprobaciones por repo
  secretos     claves de API/tokens en el árbol actual (y en el historial con
               --historial). Nunca imprime la clave: solo fichero y tipo.
  ramas        ramas remotas sin integrar, ya integradas (borrables) o viejas.
  ficheros     grandes, .pyc/__pycache__/.DS_Store/.env/.zip, nombres «(1)».
  duplicados   ficheros idénticos (≥ 20 KB) repetidos en el árbol.
  higiene      falta README / .gitignore / LICENSE.
  ruido        proporción de commits de bots en los últimos commits.
  workflows    sintaxis de .github/workflows/*.yml.
  enlaces      enlaces relativos rotos en .md y .html.

Códigos de salida: 0 todo bien · 1 hay avisos · 2 hay hallazgos críticos
· 3 no se pudo trabajar (sin git, directorio vacío…).
"""
import argparse
import collections
import datetime
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.request

CRIT, WARN, INFO = "CRITICO", "AVISO", "INFO"
ORDEN = {CRIT: 0, WARN: 1, INFO: 2}

PATRONES_SECRETOS = [
    ("clave de Anthropic", r"sk-ant-[a-z0-9]+-[A-Za-z0-9_-]{40,}"),
    ("clave de OpenAI", r"sk-(?!ant-)(proj-)?[A-Za-z0-9_-]{40,}"),
    ("token de GitHub", r"gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{50,}"),
    ("clave de AWS", r"AKIA[0-9A-Z]{16}"),
    ("clave de Google", r"AIza[0-9A-Za-z_-]{35}"),
    ("clave de fal.ai", r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}:[0-9a-f]{32}"),
    ("clave privada", r"-----BEGIN ([A-Z]+ )?PRIVATE KEY-----"),
]
RE_RELLENO = re.compile(r"(.)\1{7,}")          # xxxxxxxx, ........ → marcador de posición
NOMBRES_MALOS = re.compile(r"(__pycache__/|\.py[co]$|\.DS_Store$|(^|/)\.env(\.(?!example$|sample$|template$)[^/]*)?$|Thumbs\.db$)")
NOMBRE_COPIA = re.compile(r" \(\d+\)(\.[A-Za-z0-9]+)?$")


def git(repo, *args, check=False):
    r = subprocess.run(["git", "-C", repo] + list(args), stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE, universal_newlines=True,
                       errors="replace")
    if check and r.returncode:
        raise RuntimeError(r.stderr.strip())
    return r.stdout if r.returncode == 0 else ""


def hallazgo(sev, codigo, msg, extra=None):
    return {"sev": sev, "codigo": codigo, "msg": msg, "extra": extra or []}


# ---------------------------------------------------------------- comprobaciones
def rama_por_defecto(repo):
    ref = git(repo, "symbolic-ref", "--short", "refs/remotes/origin/HEAD").strip()
    if ref:
        return ref
    for c in ("origin/main", "origin/master"):
        if git(repo, "rev-parse", "--verify", "-q", c).strip():
            return c
    return git(repo, "rev-parse", "--abbrev-ref", "HEAD").strip() or "HEAD"


def comprobar_secretos(repo, historial):
    out = []
    revs = [["HEAD"]]
    if historial:
        todos = git(repo, "rev-list", "--all").split()
        revs = [todos[i:i + 150] for i in range(0, len(todos), 150)]
    vistos = {}
    for nombre, pat in PATRONES_SECRETOS:
        for grupo in revs:
            txt = git(repo, "grep", "-IEn", "-e", pat, *grupo, "--")
            for linea in txt.splitlines():
                # formato: <rev>:<ruta>:<nº>:<texto>; no se conserva el texto
                partes = linea.split(":", 3)
                if len(partes) < 4:
                    continue
                coinc = re.search(pat, partes[3])
                if not coinc or RE_RELLENO.search(coinc.group(0)):
                    continue
                clave = (nombre, partes[1])
                vistos.setdefault(clave, set()).add(partes[0][:7] if historial else "HEAD")
    agrupado = collections.defaultdict(list)
    for (nombre, ruta), revs_ in sorted(vistos.items()):
        agrupado[nombre].append(ruta if not historial else "%s (%d commits)" % (ruta, len(revs_)))
    for nombre, rutas in agrupado.items():
        out.append(hallazgo(CRIT, "secretos",
                            "Posible %s en %d fichero(s)%s: revócala y retírala del repo"
                            % (nombre, len(rutas), " (historial incluido)" if historial else ""),
                            rutas[:10]))
    return out


def comprobar_ramas(repo, dias):
    out, defecto = [], rama_por_defecto(repo)
    ahora = datetime.datetime.now(datetime.timezone.utc)
    salida = git(repo, "for-each-ref", "--format=%(refname:short)|%(committerdate:iso-strict)",
                 "refs/remotes/origin")
    for linea in salida.splitlines():
        nombre, _, fecha = linea.partition("|")
        if nombre in ("origin", "origin/HEAD", defecto) or not fecha:
            continue
        adelante = git(repo, "rev-list", "--count", "%s..%s" % (defecto, nombre)).strip() or "0"
        unicos = sum(1 for l in git(repo, "cherry", defecto, nombre).splitlines() if l.startswith("+"))
        try:
            edad = (ahora - datetime.datetime.fromisoformat(fecha)).days
        except ValueError:
            edad = 0
        if int(adelante) == 0:
            out.append(hallazgo(INFO, "ramas", "%s ya está integrada en %s: se puede borrar" % (nombre, defecto)))
        elif unicos == 0:
            out.append(hallazgo(INFO, "ramas", "%s: sus %s commit(s) ya están aplicados en %s (cherry-pick/rebase): borrable"
                                % (nombre, adelante, defecto)))
        else:
            sev = WARN
            out.append(hallazgo(sev, "ramas", "%s tiene %d commit(s) sin integrar en %s (último hace %d días)"
                                % (nombre, unicos, defecto, edad)))
        if edad > dias and int(adelante) > 0:
            out.append(hallazgo(WARN, "ramas", "%s lleva %d días sin actividad (umbral %d)" % (nombre, edad, dias)))
    return out


def archivos_versionados(repo):
    return [f for f in git(repo, "ls-files", "-z").split("\0") if f]


def comprobar_ficheros(repo, ficheros, limite_mb):
    out, grandes, malos, copias, espacios = [], [], [], [], 0
    for f in ficheros:
        ruta = os.path.join(repo, f)
        try:
            tam = os.path.getsize(ruta)
        except OSError:
            continue
        if tam > limite_mb * 1024 * 1024:
            grandes.append("%s (%.1f MB)" % (f, tam / 1048576))
        if NOMBRES_MALOS.search(f):
            malos.append(f)
        if NOMBRE_COPIA.search(f):
            copias.append(f)
        if " " in f:
            espacios += 1
    if grandes:
        out.append(hallazgo(WARN, "ficheros", "%d fichero(s) de más de %d MB" % (len(grandes), limite_mb), grandes[:10]))
    if malos:
        out.append(hallazgo(WARN, "ficheros", "%d fichero(s) que no deberían versionarse (.pyc, __pycache__, .DS_Store, .env…)" % len(malos), malos[:10]))
    if copias:
        out.append(hallazgo(WARN, "ficheros", "%d nombre(s) tipo «archivo (1)» (descargas duplicadas)" % len(copias), copias[:10]))
    if espacios:
        out.append(hallazgo(INFO, "ficheros", "%d fichero(s) con espacios en el nombre" % espacios))
    return out


def comprobar_duplicados(repo, ficheros, minimo=20 * 1024):
    grupos = collections.defaultdict(list)
    for f in ficheros:
        ruta = os.path.join(repo, f)
        try:
            if os.path.islink(ruta) or os.path.getsize(ruta) < minimo:
                continue
            with open(ruta, "rb") as fh:
                grupos[hashlib.sha1(fh.read()).hexdigest()].append((f, os.path.getsize(ruta)))
        except OSError:
            continue
    rep = [(len(v) - 1) * v[0][1] for v in grupos.values() if len(v) > 1]
    total = sum(rep)
    if total < 100 * 1024:
        return []
    top = sorted((v for v in grupos.values() if len(v) > 1), key=lambda v: -(len(v) - 1) * v[0][1])[:5]
    det = ["%d copias × %.0f KB: %s%s" % (len(v), v[0][1] / 1024, v[0][0], " …" if len(v) > 1 else "") for v in top]
    return [hallazgo(WARN, "duplicados", "%.0f KB repetidos en ficheros idénticos ≥ 20 KB" % (total / 1024), det)]


def comprobar_higiene(repo, ficheros):
    nombres = {f.split("/")[0].lower() for f in ficheros if "/" not in f}
    out = []
    if not any(n.startswith("readme") for n in nombres):
        out.append(hallazgo(WARN, "higiene", "Falta README en la raíz"))
    if ".gitignore" not in nombres:
        out.append(hallazgo(WARN, "higiene", "Falta .gitignore en la raíz"))
    if not any(n.startswith("license") or n.startswith("licence") for n in nombres):
        out.append(hallazgo(INFO, "higiene", "No tiene LICENSE (decisión del autor si el repo es público)"))
    return out


def comprobar_ruido(repo):
    autores = git(repo, "log", "-n", "200", "--format=%an").splitlines()
    if len(autores) < 20:
        return []
    bots = sum(1 for a in autores if a.endswith("[bot]"))
    if bots * 100 >= len(autores) * 30:
        return [hallazgo(INFO, "ruido", "El %d %% de los últimos %d commits son de bots" % (bots * 100 // len(autores), len(autores)))]
    return []


def comprobar_workflows(repo, ficheros):
    wf = [f for f in ficheros if re.match(r"\.github/workflows/[^/]+\.ya?ml$", f)]
    if not wf:
        return []
    try:
        import yaml
    except ImportError:
        return [hallazgo(INFO, "workflows", "%d workflow(s); instala PyYAML para validar su sintaxis" % len(wf))]
    out = []
    for f in wf:
        try:
            with open(os.path.join(repo, f), encoding="utf-8") as fh:
                d = yaml.safe_load(fh)
            if not isinstance(d, dict) or "jobs" not in d:
                out.append(hallazgo(WARN, "workflows", "%s: no define «jobs»" % f))
        except Exception as e:                      # noqa: BLE001
            out.append(hallazgo(CRIT, "workflows", "%s: YAML no válido (%s)" % (f, str(e).splitlines()[0])))
    return out


RE_MD = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
RE_HTML = re.compile(r"""(?:href|src)\s*=\s*["']([^"']+)["']""")


def enlace_relativo(url):
    u = url.split("#")[0].split("?")[0]
    if not u or u.startswith(("//", "/")) or re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", u):
        return None                                  # absoluto, esquema (http:, mailto:, about:…) o vacío
    if any(c in u for c in "{}$<>`") or "__" in u:
        return None
    return u


def comprobar_enlaces(repo, ficheros, maximo=15):
    rotos = []
    for f in ficheros:
        ext = f.lower().rsplit(".", 1)[-1] if "." in f else ""
        if ext not in ("md", "html", "htm"):
            continue
        ruta = os.path.join(repo, f)
        try:
            with open(ruta, encoding="utf-8", errors="replace") as fh:
                txt = fh.read()
        except OSError:
            continue
        if ext == "md":
            txt = re.sub(r"```.*?```", "", txt, flags=re.S)
            txt = re.sub(r"`[^`\n]*`", "", txt)  # ejemplos entre comillas invertidas
        urls = RE_MD.findall(txt) if ext == "md" else RE_HTML.findall(txt)
        for url in urls:
            rel = enlace_relativo(url)
            if rel is None:
                continue
            destino = os.path.normpath(os.path.join(os.path.dirname(ruta), rel.replace("%20", " ")))
            if not os.path.exists(destino):
                rotos.append("%s → %s" % (f, url))
    if not rotos:
        return []
    return [hallazgo(WARN, "enlaces", "%d enlace(s) relativo(s) que no apuntan a nada" % len(rotos), rotos[:maximo])]


def auditar(repo, a):
    ficheros = archivos_versionados(repo)
    hs = []
    hs += comprobar_secretos(repo, a.historial)
    hs += comprobar_ramas(repo, a.dias)
    hs += comprobar_ficheros(repo, ficheros, a.mb)
    hs += comprobar_duplicados(repo, ficheros)
    hs += comprobar_higiene(repo, ficheros)
    hs += comprobar_ruido(repo)
    hs += comprobar_workflows(repo, ficheros)
    hs += comprobar_enlaces(repo, ficheros)
    hs.sort(key=lambda h: (ORDEN[h["sev"]], h["codigo"]))
    return hs


# ---------------------------------------------------------------- descubrimiento
def repos_en(directorio):
    directorio = os.path.abspath(directorio)
    if os.path.isdir(os.path.join(directorio, ".git")):
        return [directorio]
    return sorted(os.path.join(directorio, d) for d in os.listdir(directorio)
                  if os.path.isdir(os.path.join(directorio, d, ".git")))


def clonar_publicos(usuario, destino):
    os.makedirs(destino, exist_ok=True)
    pagina, hechos = 1, []
    while True:
        url = "https://api.github.com/users/%s/repos?type=public&per_page=100&page=%d" % (usuario, pagina)
        with urllib.request.urlopen(url, timeout=30) as r:
            datos = json.load(r)
        if not datos:
            break
        for d in datos:
            if d.get("archived"):
                continue
            ruta = os.path.join(destino, d["name"])
            if os.path.isdir(os.path.join(ruta, ".git")):
                git(ruta, "fetch", "--quiet", "--depth", "200", "origin")
            else:
                subprocess.run(["git", "clone", "--quiet", "--depth", "200", "--no-single-branch",
                                d["clone_url"], ruta], check=False)
            hechos.append(ruta)
        pagina += 1
    return hechos


# ---------------------------------------------------------------- salida
def imprimir(resultados, color):
    c = (lambda k, t: t) if not color else (lambda k, t: "\033[%sm%s\033[0m" % ({CRIT: "1;31", WARN: "33", INFO: "36"}.get(k, "1"), t))
    cuenta = collections.Counter()
    for repo, hs in resultados.items():
        print("\n=== %s" % os.path.basename(repo))
        if not hs:
            print("  sin hallazgos")
        for h in hs:
            cuenta[h["sev"]] += 1
            print("  %s [%s] %s" % (c(h["sev"], "%-7s" % h["sev"]), h["codigo"], h["msg"]))
            for e in h["extra"]:
                print("            · %s" % e)
    print("\nResumen: %d crítico(s), %d aviso(s), %d informativo(s) en %d repo(s)."
          % (cuenta[CRIT], cuenta[WARN], cuenta[INFO], len(resultados)))
    return cuenta


def main():
    ap = argparse.ArgumentParser(description="Revisa (solo lectura) los repos de RafaUMH2110.")
    ap.add_argument("-d", "--directorio", default=".", help="repo, o carpeta que contiene los clones (por defecto, .)")
    ap.add_argument("--clonar", metavar="USUARIO", help="clona/actualiza en DIRECTORIO los repos públicos no archivados de USUARIO")
    ap.add_argument("--historial", action="store_true", help="busca secretos también en todo el historial (más lento)")
    ap.add_argument("--dias", type=int, default=60, help="días sin actividad para avisar de una rama (60)")
    ap.add_argument("--mb", type=int, default=5, help="tamaño (MB) a partir del cual un fichero es «grande» (5)")
    ap.add_argument("--json", action="store_true", help="salida en JSON")
    ap.add_argument("--no-color", action="store_true")
    a = ap.parse_args()

    try:
        subprocess.run(["git", "--version"], stdout=subprocess.DEVNULL, check=True)
    except (OSError, subprocess.CalledProcessError):
        print("ERROR: falta git", file=sys.stderr)
        return 3
    try:
        repos = clonar_publicos(a.clonar, a.directorio) if a.clonar else repos_en(a.directorio)
    except Exception as e:                           # noqa: BLE001
        print("ERROR: %s" % e, file=sys.stderr)
        return 3
    if not repos:
        print("ERROR: no hay repositorios git en %s" % os.path.abspath(a.directorio), file=sys.stderr)
        return 3

    resultados = collections.OrderedDict((r, auditar(r, a)) for r in repos)
    if a.json:
        print(json.dumps({os.path.basename(r): hs for r, hs in resultados.items()}, ensure_ascii=False, indent=2))
        cuenta = collections.Counter(h["sev"] for hs in resultados.values() for h in hs)
    else:
        cuenta = imprimir(resultados, sys.stdout.isatty() and not a.no_color and os.name != "nt")
    return 2 if cuenta[CRIT] else (1 if cuenta[WARN] else 0)


if __name__ == "__main__":
    sys.exit(main())
