# telemetria/home

**Autor:** Rafa · Departamento de Ingeniería de Sistemas y Automática · Universidad Miguel Hernández de Elche · r.puerto@umh.es
*Generado con IA · Revisado por el autor*

TeleHome: telemetría y control del hogar (enchufes Wi-Fi con medidor de consumo Energeeks EG-EW008MC / EG-EW009MC, Tuya; también sensores, luces y persianas).

| Carpeta | Para qué sirve |
|---|---|
| [`telehome-servicio/`](telehome-servicio/README.md) | Servicio (0.13.0): interfaz web, luces con escenas, grupos, transiciones y temporizadores (que sobreviven a un reinicio), estancias con nombre, histórico SQLite, modo local y modo nube (API de Tuya IoT), programaciones, niveles de acceso (administrador / usuario de confianza), macOS y Linux (systemd). Se instala como `telehome`. |
| [`telehome-pruebas/`](telehome-pruebas/README.md) | Pruebas preliminares por línea de órdenes (estado, encender, apagar, vigilar a CSV), antes de instalar el servicio. Ver su [manual](telehome-pruebas/MANUAL.md). |

Las apps cliente (web genérica, iPhone e iPad) están en el repo [`apps`](https://github.com/RafaUMH2110/apps/tree/main/telemetria/home). Las lecturas de la estación meteorológica están en [`../meteo/`](../meteo/README.md).
