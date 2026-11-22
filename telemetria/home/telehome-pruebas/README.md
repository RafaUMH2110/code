# TeleHome · versión vscode

Pruebas preliminares, **desde la línea de órdenes y desde VS Code**, de los enchufes Wi-Fi Energeeks
EG-EW008MC (el pack de 3 se vende como EG-EW009MC) u otros enchufes Tuya: consultar el estado, encender, apagar,
conmutar, registrar lecturas a CSV y ver los datos crudos (DPS) de cada enchufe. Hasta **7 enchufes**.

Es un único fichero Python, [`telehome-pruebas.py`](telehome-pruebas.py), comentado y documentado
por secciones. No tiene interfaz web ni base de datos: sirve para comprobar credenciales, códigos y escalas
**antes** de instalar [`telehome-servicio`](../telehome-servicio/).

## Inicio rápido

```bash
git clone --depth 1 --filter=blob:none --sparse https://github.com/RafaUMH2110/code.git
cd code && git sparse-checkout set telemetria/home/telehome-pruebas
cd telemetria/home/telehome-pruebas

python3 telehome-pruebas.py --simular estado      # sin enchufes ni TinyTuya
pip install tinytuya                                       # para los modos local y nube
cp config-pruebas.example.json config-pruebas.json         # y edítalo (también puedes editar las variables del .py)
python3 telehome-pruebas.py estado
```

En VS Code, abre esta carpeta y pulsa F5: hay configuraciones para estado, encender, apagar, conmutar, vigilar,
datos crudos y dispositivos de la nube. Las tareas crean el `.venv` y lanzan `pytest`.

## Contenido

| Fichero | Para qué |
|---|---|
| `telehome-pruebas.py` | La herramienta (modos local, nube y simulado) |
| `config-pruebas.example.json` | Plantilla de configuración; cópiala como `config-pruebas.json` (no se versiona) |
| `MANUAL.md` | Manual completo: campos, órdenes, prioridad de la configuración, códigos de salida |
| `.vscode/` | Ejecución, depuración y tareas de VS Code |
| `tests/` | 15 pruebas automáticas (`python3 -m pytest -q`), con enchufes simulados y un cliente de nube falso |

Los modos local y nube se han probado solo con clientes simulados, no con enchufes reales.
