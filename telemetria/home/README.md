# telemetria/home

**Autor:** Rafa · Departamento de Ingeniería de Sistemas y Automática · Universidad Miguel Hernández de Elche · r.puerto@umh.es
*Generado con IA · Revisado por el autor*

TeleMet Enchufes: telemetría y control de enchufes Wi-Fi con medidor de consumo Energeeks EG-EW008MC / EG-EW009MC (Tuya). Tres versiones autocontenidas; cada una usa la misma carpeta de datos, así que **no las instales a la vez**.

| Carpeta | Para qué sirve |
|---|---|
| [`telehome-enchufes-local/`](telehome-enchufes-local/README.md) | Versión 0.1.0: solo macOS y solo red local, con interfaz web e histórico SQLite. |
| [`telehome-enchufes-nube/`](telehome-enchufes-nube/README.md) | Versión 0.2.0: añade modo nube (API de Tuya IoT), Linux (systemd) y contraseña opcional. |
| [`telehome-enchufes-vscode/`](telehome-enchufes-vscode/README.md) | Pruebas preliminares por línea de órdenes (estado, encender, apagar, vigilar a CSV). Ver su [manual](telehome-enchufes-vscode/MANUAL.md). |

Los nombres internos del programa (paquete `telemet_enchufes`, orden y servicio `telemet-enchufes`, carpeta de datos) no cambian, para no romper instalaciones existentes.

Las lecturas de la estación meteorológica están en [`../meteo/`](../meteo/README.md).
