# Pruebas preliminares de enchufes: `telemet-enchufes-pruebas.py`

Herramienta de línea de órdenes, en un único fichero Python, para probar los enchufes Energeeks EG-EW008MC
(pack EG-EW009MC) u otros enchufes Tuya **antes** de instalar la interfaz web de TeleMet Enchufes. Sirve para
comprobar credenciales, ver qué datos devuelve cada enchufe, encenderlo o apagarlo y registrar lecturas.

Es independiente: puedes copiar el `.py` (y, si quieres, su JSON) a cualquier carpeta. Pertenece a la versión «vscode» de TeleMet Enchufes; las versiones con interfaz web son [`telemet-enchufes-local`](../telemet-enchufes-local/) y [`telemet-enchufes-nube`](../telemet-enchufes-nube/).

## 1. Requisitos

- Python 3.9 o superior.
- TinyTuya para los modos `local` y `nube`: `pip install tinytuya`. El modo `simulado` no necesita nada.

En VS Code: *Terminal → Ejecutar tarea… → Crear .venv e instalar dependencias* y elige `.venv` como intérprete
(*Python: Select Interpreter*).

## 2. Modos de cada enchufe

| Modo | Cómo habla con el enchufe | Necesita |
|---|---|---|
| `local` | Red local, TCP 6668 (TinyTuya) | Misma red, `dev_id`, `local_key`; `ip` (o `Auto`) y `version` |
| `nube` | API de Tuya IoT (TinyTuya `Cloud`) | `dev_id` y las credenciales `access_id` / `access_secret` del proyecto |
| `simulado` | Nada: datos ficticios | Solo `dev_id` (cualquiera de 8+ caracteres) |

`--simular` trata **todos** los enchufes como simulados (y, si no hay ninguno, usa tres de demostración).

El modo nube exige que los enchufes estén en **Smart Life** o **Tuya Smart** y que esa cuenta esté enlazada al
proyecto de iot.tuya.com (ver el README de [`telemet-enchufes-nube`](../telemet-enchufes-nube/README.md)). Con la app Energeeks 3.0 normalmente no funciona.

## 3. Configuración: código o JSON

Hay dos formas, combinables:

**a) Variables del código.** Al principio del script, sección *1. CONFIGURACIÓN EDITABLE*:

```python
NUBE = {"region": "eu", "access_id": "abcd1234…", "access_secret": ""}
ENCHUFES = [
    {"nombre": "Nevera", "modo": "nube", "dev_id": "bf0123456789abcdefxyz"},
    {"nombre": "Router", "modo": "nube", "dev_id": "bf98765…", "protegido": True},
]
OPCIONES = {"intervalo_vigilancia": 60, "tiempo_espera": 5, "tiempo_busqueda": 12}
```

**b) Fichero JSON.** Copia `config-pruebas.example.json` como `config-pruebas.json` (está en `.gitignore`) o indica
otro con `--config ruta.json`. Mismas secciones: `nube`, `opciones`, `enchufes`.

**Prioridad** (el último gana): variables del código → JSON → opciones de la línea de órdenes.
`nube` y `opciones` del JSON se fusionan **campo a campo** con las del código; la lista `enchufes` del JSON, si
existe, **sustituye** a la del código. `--sin-json` ignora el JSON. `config` muestra el resultado y su origen.

**Secreto fuera de los ficheros:** deja `access_secret` vacío y exporta `TUYA_ACCESS_SECRET` (en VS Code se puede
poner en `"env"` de la configuración de `launch.json`).

### Campos de cada enchufe

| Campo | Obligatorio | Descripción |
|---|---|---|
| `nombre` | sí | Nombre único (se usa para referirse a él) |
| `modo` | sí | `local`, `nube` o `simulado` |
| `dev_id` | sí | Device ID de Tuya |
| `local_key` | modo local | Local Key (16 caracteres) |
| `ip` | no | IPv4 o `Auto` (búsqueda por difusión UDP); solo modo local |
| `version` | no | Protocolo local: 3.1 a 3.5 (por defecto 3.3) |
| `protegido` | no | `true` impide apagarlo o conmutarlo sin `--forzar` |
| `dp_interruptor`, `dp_potencia`, `dp_tension`, `dp_corriente` | no | Números de DPS en modo local (1, 19, 20, 18) |
| `codigo_interruptor`, `codigo_potencia`, `codigo_tension`, `codigo_corriente` | no | Códigos en modo nube (`switch_1`, `cur_power`, `cur_voltage`, `cur_current`) |
| `escala_potencia`, `escala_tension`, `escala_corriente` | no | Divisores a W, V y A (10, 10, 1000) |
| `comentario` | no | Texto libre, se ignora |

Como máximo **7 enchufes**; nombres y Device ID no pueden repetirse.

## 4. Órdenes

Los enchufes se indican por **nombre** (sin distinguir mayúsculas), **posición** (1-7), **Device ID** o `todos`.

| Orden | Qué hace |
|---|---|
| `listar` | Enchufes configurados (sin claves) |
| `config` | Configuración efectiva en JSON, con los secretos ocultos y el origen de cada sección |
| `estado [ENCHUFE…]` | Estado, potencia, tensión y corriente (todos por defecto) |
| `encender ENCHUFE…` | Enciende y comprueba el estado resultante |
| `apagar ENCHUFE…` | Apaga y comprueba (`--forzar` para protegidos, `--si` con `todos`) |
| `conmutar ENCHUFE…` | Invierte el estado actual (mismas protecciones que `apagar`) |
| `vigilar [ENCHUFE…] [-i S] [-n N] [--csv F]` | Lecturas periódicas; `-n 0` = sin fin (Ctrl+C) |
| `dps ENCHUFE` | Datos crudos y qué clave se usa para cada magnitud |
| `buscar [--tiempo S]` | Enchufes Tuya en la red local (Device ID, IP, versión) |
| `nube-dispositivos [--guardar] [--todos]` | Dispositivos de la cuenta enlazada; `--guardar` los añade al JSON |

Opciones generales (antes de la orden): `-c/--config`, `--sin-json`, `--simular`, `--json`, `-v` (`-vv` también
depura TinyTuya). `encender/apagar/conmutar` aceptan `--espera S` (2 s): tiempo antes de verificar el estado.

Ejemplos:

```bash
python telemet-enchufes-pruebas.py --simular estado
python telemet-enchufes-pruebas.py nube-dispositivos --guardar     # rellena el JSON desde la nube
python telemet-enchufes-pruebas.py estado
python telemet-enchufes-pruebas.py dps Nevera                      # ¿cuadran los códigos y escalas?
python telemet-enchufes-pruebas.py apagar 2 && python telemet-enchufes-pruebas.py encender 2
python telemet-enchufes-pruebas.py vigilar todos -i 60 -n 30 --csv lecturas.csv
python telemet-enchufes-pruebas.py --json estado > estado.json
```

## 5. Visual Studio Code

Abre esta carpeta (`telemet-enchufes-vscode/`) en VS Code. Ya incluye:

- `.vscode/launch.json`: configuraciones *Pruebas: estado de todos*, *estado (simulado)*, *encender…*, *apagar…*,
  *conmutar…* (piden el enchufe), *vigilar (10 lecturas a CSV)*, *datos crudos*, *dispositivos de la nube*,
  y *orden libre…* (escribes los argumentos). Con F5 se puede
  poner un punto de interrupción en cualquier parte del script (p. ej. en `interpretar()` o `ConectorNube`).
- `.vscode/tasks.json`: crear `.venv`, ejecutar `pytest` y consultar estado/configuración.
- `.vscode/settings.json`: intérprete `.venv` y pytest activado.

## 6. Códigos de salida

| Código | Significado |
|---|---|
| 0 | Correcto |
| 1 | Algún enchufe no respondió o no quedó en el estado pedido |
| 2 | Error de configuración o de uso (enchufe desconocido, protegido, JSON no válido…) |
| 3 | Falta TinyTuya |
| 130 | Interrumpido con Ctrl+C |

## 7. Avisos

- **Cupo de la nube.** Cada lectura en modo nube gasta 2 llamadas por enchufe (estado + conexión) y cada orden, 1-3.
  La herramienta muestra cuántas ha hecho. Con `vigilar` en modo nube el intervalo mínimo es 60 s.
- **Estado «desconectado» en la nube.** Si el enchufe no está conectado, la nube devuelve el *último estado
  conocido*; la herramienta lo marca como «NO en línea» para que no se tome por actual.
- **Cuidado con lo que apagas a distancia.** Si apagas el enchufe del que depende el router o la Wi-Fi, ya no podrás
  volver a encenderlo desde fuera. Márcalo con `"protegido": true`.
- La Local Key cambia si el enchufe se vuelve a emparejar; repite `nube-dispositivos --guardar`.
- El estado on/off de los enchufes simulados se guarda en un fichero temporal, así que persiste entre ejecuciones.

## 8. Estructura del código

1. Configuración editable · 2. Constantes · 3. Modelo de datos (`Enchufe`, `Lectura`…, dataclasses inmutables) ·
4. Carga y validación (`cargar_configuracion`, `resolver_enchufes`) · 5. Conectores (`Conector` abstracto y
`ConectorLocal`, `ConectorNube` con `SesionNube`, `ConectorSimulado`) · 6. Presentación (`Salida`: tabla o JSON) ·
7. Órdenes (`orden_*`) · 8. Línea de órdenes (`construir_parser`, `main`).

Para añadir una orden: escribe `orden_xxx(args, cfg, out) -> int` en la sección 7 y regístrala en `construir_parser`.

Pruebas automáticas: `tests/test_pruebas_cli.py` (modo simulado y nube con un cliente falso).

---
Rafa · Departamento de Ingeniería de Sistemas y Automática · Universidad Miguel Hernández de Elche · r.puerto@umh.es
Generado con IA · Revisado por el autor
