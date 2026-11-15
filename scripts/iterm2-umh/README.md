# iterm2-umh — iTerm2: tema, perfiles por servidor y SSH con claves

**Autor:** Rafa · Departamento de Ingeniería de Sistemas y Automática · Universidad Miguel Hernández de Elche · r.puerto@umh.es
*Generado con IA · Revisado por el autor*

Configuración completa de **iTerm2** en macOS a partir de un inventario de servidores
en CSV: un tema de color propio, un perfil por servidor con su color de pestaña y su
distintivo, y acceso SSH sin contraseña mediante claves (lo que coloquialmente
llamamos «certificados»).

El inventario es la única fuente: de él salen los perfiles dinámicos de iTerm2 y la
configuración SSH, y con él se crean y reparten las claves. Se rellena cómodamente en
una hoja de cálculo y se exporta como CSV.

## Contenido

| Fichero | Para qué sirve |
|---|---|
| `generar_perfiles.py` | Del CSV a `perfiles/UMH-Perfiles.json` (perfiles dinámicos de iTerm2) y `ssh/umh.conf` (para `~/.ssh/config.d/`). Valida el lote y no escribe nada si hay errores. Con `--instalar` lo pone en su sitio |
| `generar_claves.py` | Crea una clave por cada valor distinto de la columna `clave`, la guarda en el Llavero de macOS, la copia a cada servidor con `ssh-copy-id` y comprueba que entra sin contraseña. `--solo` y `--grupo` para ir máquina a máquina |
| `umh_inventario.py` | Módulo compartido: lee el CSV y lo valida. Los dos generadores entienden exactamente lo mismo por una hoja |
| `instalar-iterm2.sh` | Primera vez: instala la tipografía, importa los temas y fija el perfil predeterminado |
| `diagnostico.sh` | Cuando iTerm2 no aplica la fuente o el tamaño: dice por qué (perfil predeterminado, nombre PostScript de la fuente, restauración de ventanas) |
| `colores/*.itermcolors` | Tema «UMH Elegante» en sus dos variantes: oscuro para el día a día, claro para proyectar en clase |
| `datos/servidores-ejemplo.csv` | Inventario de ejemplo con la leyenda de las columnas. Cópialo a `datos/servidores.csv` y edítalo |
| `ejemplos/` | Lo que produce el inventario de ejemplo, para verlo sin ejecutar nada |
| `MANUAL.md` | Guía completa: apariencia y tipografía, perfiles dinámicos, SSH con claves, certificados firmados por una CA, resolución de problemas y el inventario en CSV |

## Uso rápido

```bash
bash instalar-iterm2.sh                      # solo la primera vez
cp datos/servidores-ejemplo.csv datos/servidores.csv   # y edítalo
python3 generar_perfiles.py                  # genera y valida, sin instalar
python3 generar_perfiles.py --instalar       # perfiles + ~/.ssh/config.d/umh.conf
python3 generar_claves.py --dry-run          # qué haría con las claves
python3 generar_claves.py                    # crear, guardar y repartir
```

`generar_perfiles.py --instalar` **no sobrescribe tu `~/.ssh/config`**: escribe
`~/.ssh/config.d/umh.conf` y solo añade, al principio de tu config, la línea
`Include config.d/*.conf` (al principio porque SSH se queda con el primer valor de
cada opción).

## Tu inventario no se versiona

`datos/servidores.csv`, `perfiles/` y `ssh/` están en el `.gitignore` de esta carpeta:
llevan direcciones internas, nombres de usuario y el mapa de qué clave abre qué
máquina. Aquí solo se versiona `datos/servidores-ejemplo.csv`, con direcciones de
documentación (RFC 5737 y RFC 2606) que no corresponden a ningún equipo real. Es el
mismo criterio que el repositorio aplica a `.env` y `.env.example`.

## Requisitos

macOS con iTerm2 3.x, Python 3 y, para instalar la tipografía automáticamente,
Homebrew (`brew install --cask font-jetbrains-mono-nerd-font`). Los scripts no
instalan dependencias de Python: usan solo la biblioteca estándar.
