# home — telemetría doméstica

Apps de telemetría para la casa, separadas de los scripts de la estación meteorológica que hay en
[`telemetria/`](../README.md). Hoy contiene **TeleMet Enchufes**: lectura de potencia, tensión y corriente, y
control (encender/apagar), de hasta 7 enchufes Wi-Fi Energeeks EG-EW008MC / EG-EW009MC (Tuya).

Cada versión es una carpeta autocontenida (código, `.vscode/`, README y pruebas) que se abre como carpeta raíz en VS Code:

| Carpeta | Versión | Qué es |
|---|---|---|
| [`telemet-enchufes-local/`](telemet-enchufes-local/) | 0.1.0 | macOS, solo red local, con interfaz web e histórico SQLite. |
| [`telemet-enchufes-nube/`](telemet-enchufes-nube/) | 0.2.0 | Añade modo nube (API de Tuya IoT), instalador para Linux (systemd) y contraseña opcional. Es la que sirve para una VM de Azure. |
| [`telemet-enchufes-vscode/`](telemet-enchufes-vscode/) | — | Script único de pruebas por línea de órdenes (estado, encender, apagar, vigilar a CSV, datos crudos), configurable por JSON y por variables del código. Sirve para probar antes de instalar las otras. |

`local` y `nube` usan la misma carpeta de datos y el mismo nombre de servicio: instala solo una de las dos.

Para descargar solo una carpeta (ejemplo con `nube`):

```bash
git clone --depth 1 --filter=blob:none --sparse https://github.com/RafaUMH2110/code.git
cd code && git sparse-checkout set telemetria/home/telemet-enchufes-nube
```
