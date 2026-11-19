# telemetria/home

**Autor:** Rafa · Departamento de Ingeniería de Sistemas y Automática · Universidad Miguel Hernández de Elche · r.puerto@umh.es
*Generado con IA · Revisado por el autor*

TeleMet Enchufes: telemetría y control de enchufes Wi-Fi con medidor de consumo Energeeks EG-EW008MC / EG-EW009MC (Tuya).

| Carpeta | Para qué sirve |
|---|---|
| [`telehome-enchufes/`](telehome-enchufes/README.md) | Aplicación (0.2.0): interfaz web, histórico SQLite, modo local y modo nube (API de Tuya IoT), macOS y Linux (systemd) y contraseña opcional. Sustituye a la antigua versión «local» (0.1.0), que ya está incluida. |
| [`telehome-enchufes-vscode/`](telehome-enchufes-vscode/README.md) | Pruebas preliminares por línea de órdenes (estado, encender, apagar, vigilar a CSV), antes de instalar la aplicación. Ver su [manual](telehome-enchufes-vscode/MANUAL.md). |

Los nombres internos del programa (paquete `telemet_enchufes`, orden y servicio `telemet-enchufes`, carpeta de datos) no cambian, para no romper instalaciones existentes.

Las lecturas de la estación meteorológica están en [`../meteo/`](../meteo/README.md).
