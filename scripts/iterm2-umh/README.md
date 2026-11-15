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
| `instalar-iterm2.sh` | Primera vez en un ordenador: pregunta cómo se llama (`-m "iMac despacho"`), instala los perfiles, ofrece la shell integration de iTerm2 y fija el perfil predeterminado (los temas se importan solo con `--colores`) |
| `diagnostico.sh` | Cuando iTerm2 no aplica la fuente o el tamaño: dice por qué (perfil predeterminado, nombre PostScript de la fuente, restauración de ventanas) |
| `colores/*.itermcolors` | Tema «UMH Elegante» en sus dos variantes: oscuro para el día a día, claro para proyectar en clase |
| `datos/servidores-ejemplo.csv` | Inventario de ejemplo con la leyenda de las columnas. Cópialo a `datos/servidores.csv` y edítalo |
| `ejemplos/` | Lo que produce el inventario de ejemplo, para verlo sin ejecutar nada |
| `MANUAL.md` | Guía completa: apariencia y tipografía, perfiles dinámicos, SSH con claves, certificados firmados por una CA, resolución de problemas y el inventario en CSV |

## Uso rápido

```bash
bash instalar-iterm2.sh -m "iMac despacho"   # solo la primera vez en este equipo
cp datos/servidores-ejemplo.csv datos/servidores.csv   # y edítalo
python3 generar_perfiles.py                  # genera y valida, sin instalar
python3 generar_perfiles.py --instalar       # perfiles + ~/.ssh/config.d/umh.conf
python3 generar_claves.py --dry-run          # qué haría con las claves
python3 generar_claves.py                    # crear, guardar y repartir
```

El nombre que le das al equipo se guarda en `datos/maquina.txt` y lo usan los dos
generadores: sale como distintivo en las sesiones locales y como comentario de las
claves SSH que se creen aquí, para distinguirlas en el `authorized_keys` de los
servidores cuando lo leas dentro de dos años. Sin `-m` se pregunta, proponiendo el
nombre que macOS ya tiene configurado.

`generar_perfiles.py --instalar` **no sobrescribe tu `~/.ssh/config`**: escribe
`~/.ssh/config.d/umh.conf` y solo añade, al principio de tu config, la línea
`Include config.d/*.conf` (al principio porque SSH se queda con el primer valor de
cada opción).

## Tu inventario no se versiona

`datos/servidores.csv`, `perfiles/` y `ssh/` están en el `.gitignore` de esta carpeta:
llevan direcciones internas, nombres de usuario y el mapa de qué clave abre qué
máquina. `datos/maquina.txt` tampoco: cada ordenador tiene el suyo. Aquí solo se versiona `datos/servidores-ejemplo.csv`, con direcciones de
documentación (RFC 5737 y RFC 2606) que no corresponden a ningún equipo real. Es el
mismo criterio que el repositorio aplica a `.env` y `.env.example`.

## Requisitos

macOS con iTerm2 3.x y Python 3. La tipografía (Menlo) viene con macOS; Homebrew solo
hace falta si algún día usas una Nerd Font. Los scripts no instalan dependencias de
Python: usan solo la biblioteca estándar.

Los `.sh` llevan shebang de bash, así que se ejecutan con bash aunque tu shell sea
zsh, el de Darwin. Están escritos para funcionar igual si los lanzas con
`zsh instalar-iterm2.sh`: sin `read -p` y sin globs que puedan quedarse sin
resultados, que es donde zsh y bash se separan.

### En Linux

La parte de iTerm2 es solo de macOS, porque iTerm2 no existe en Linux:
`instalar-iterm2.sh` y `diagnostico.sh` se niegan a ejecutarse ahí, y
`generar_perfiles.py --instalar` instala solo la configuración SSH y dice que se
salta los perfiles (el JSON se genera igual, por si lo llevas a un Mac).

La parte SSH sí es útil en Linux, y el archivo generado vale en los dos sistemas: la
primera línea es un `IgnoreUnknown UseKeychain,…`, porque `UseKeychain` solo existe en
el OpenSSH de Apple y sin esa línea el `ssh` de Linux aborta con
`Bad configuration option: usekeychain` **para cualquier host**, no solo para los del
inventario. Va al principio del archivo a propósito: `ssh_config(5)` advierte de que
`IgnoreUnknown` no se aplica a lo que aparezca antes de él. `generar_claves.py` ya
distingue el sistema y usa `ssh-add` sin `--apple-use-keychain`.

Los `.itermcolors` son de iTerm2, pero los colores en hexadecimal están en el
apartado 1.2 del manual si quieres llevar la paleta a otro terminal.
