# telemet-collector-info (local y remoto por SSH)

**Autor:** Rafa · Departamento de Ingeniería de Sistemas y Automática · Universidad Miguel Hernández de Elche · r.puerto@umh.es
*Generado con IA · Revisado por el autor*

Scripts **independientes** (solo biblioteca estándar de Python 3, no necesitan el colector) que **leen y muestran todos los parámetros** de TeleMet Collector. Solo leen: no modifican nada ni consultan la API de Weather Underground.

| Script | Se ejecuta | Para qué |
|---|---|---|
| `telemet-collector-info.py` | En el servidor | Informe local |
| `telemet-collector-info-ssh.py` | En tu ordenador (CLI o VS Code) | Se conecta por SSH (contraseña o clave RSA) y muestra el informe del servidor sin instalar nada allí; admite varios servidores |

**Manual detallado: [`MANUAL.md`](MANUAL.md)** (autenticación, sudo, VS Code, automatización, solución de problemas). Ejemplos para VS Code en `vscode-ejemplo/`.

## Qué muestra

| Bloque | Contenido |
|---|---|
| Fichero de configuración | Ruta, propietario, permisos, tamaño, fecha y si empieza por BOM UTF-8 |
| Estaciones | `station_id`, `api_key` (enmascarada), de dónde sale cada dato (config.ini o variable de entorno), intervalo y llamadas/día, rutas de la base de datos y del JSON de cada estación (una o varias) |
| Lectura, ciclo, salida y log | `base_url`, `interval_s`, `timeout_s`, `backoff_*`, `duration_hours`, `mode`, `db_path`, `json_path`, `decimals`, nivel y fichero de log |
| Directorios y ficheros | Directorio de instalación; por estación, base de datos (tamaño, propietario, nº de lecturas, primera y última) y JSON (tamaño, propietario, antigüedad, lecturas) |
| Servicio systemd | Unidad, estado, arranque automático, usuario, `ExecStart`, `ReadWritePaths`, reinicios, variables de entorno de la unidad |
| Diagnóstico | Avisos y errores: credenciales de plantilla o ausentes, BOM, permisos, carpeta del JSON inexistente o sin permiso de escritura, `ReadWritePaths`, JSON antiguo, servicio parado o reiniciándose, servicio español instalado a la vez… |

Los valores se calculan con las mismas reglas que `telemet_collector.py` (rutas relativas respecto a `config.ini`, sufijo `_<ID>` con varias estaciones, `[station:ID]`, `TELEMET_*`…).

## Uso local (en el servidor)

```bash
sudo python3 telemet-collector-info.py                      # /opt/telemet-collector/config.ini
sudo python3 telemet-collector-info.py -c /ruta/config.ini
sudo python3 telemet-collector-info.py --show-key           # API Key completa
python3 telemet-collector-info.py --json                    # salida para otros programas
python3 telemet-collector-info.py --lang en                 # inglés (por defecto, según $LANG)
```

`config.ini` suele ser 600 y de `telemet`, por eso hay que usar `sudo`. Otras opciones: `--service NOMBRE`, `--no-service`, `--use-shell-env`, `--no-color`. Código de salida: 0 sin errores, 1 si hay algún error de diagnóstico, 2 si no se puede leer la configuración.

## Uso remoto (desde tu ordenador)

```bash
python3 telemet-collector-info-ssh.py rafa@192.168.0.129                 # clave o contraseña (la pide ssh)
python3 telemet-collector-info-ssh.py rafa@servidor -i ~/.ssh/id_rsa      # clave RSA
python3 telemet-collector-info-ssh.py rafa@servidor --ask-password       # contraseña pedida por el script
python3 telemet-collector-info-ssh.py srv1 srv2 --json                   # varios servidores
python3 telemet-collector-info-ssh.py rafa@servidor --check              # solo probar la conexión
```

Los dos `.py` deben estar en la misma carpeta. Necesita `ssh` en tu ordenador y `python3` (y `sudo` si no eres root) en el servidor.

La API Key se enmascara salvo con `--show-key`; no la pegues en chats ni en incidencias.
