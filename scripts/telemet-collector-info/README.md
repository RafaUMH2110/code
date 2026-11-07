# telemet-collector-info.py

**Autor:** Rafa · Departamento de Ingeniería de Sistemas y Automática · Universidad Miguel Hernández de Elche · r.puerto@umh.es
*Generado con IA · Revisado por el autor*

Script **independiente** (solo biblioteca estándar de Python 3, no necesita el colector) que **lee y muestra todos los parámetros** de TeleMet Collector. Solo lee: no modifica nada ni consulta la API de Weather Underground.

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

## Uso

```bash
sudo python3 telemet-collector-info.py                      # /opt/telemet-collector/config.ini
sudo python3 telemet-collector-info.py -c /ruta/config.ini
sudo python3 telemet-collector-info.py --show-key           # API Key completa
python3 telemet-collector-info.py --json                    # salida para otros programas
python3 telemet-collector-info.py --lang en                 # inglés (por defecto, según $LANG)
```

`config.ini` suele ser 600 y de `telemet`, por eso hay que usar `sudo`. Otras opciones: `--service NOMBRE`, `--no-service`, `--use-shell-env`, `--no-color`. Código de salida: 0 sin errores, 1 si hay algún error de diagnóstico, 2 si no se puede leer la configuración.

La API Key se enmascara salvo con `--show-key`; no la pegues en chats ni en incidencias.
