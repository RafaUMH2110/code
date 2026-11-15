# iTerm2 · Configuración elegante con perfiles y SSH por clave

Guía de la configuración incluida en este paquete: tema de color propio, tipografía,
perfiles dinámicos para cada servidor y acceso SSH sin contraseña mediante claves
(lo que coloquialmente llamamos "certificados").

```
iterm2-umh/
├── umh_inventario.py            lee y valida el inventario (lo usan los dos generadores)
├── generar_perfiles.py          -> perfiles/UMH-Perfiles.json  +  ssh/umh.conf
├── generar_claves.py            claves, Llavero de macOS y ssh-copy-id
├── instalar-iterm2.sh           fuente, temas y perfil predeterminado (primera vez)
├── diagnostico.sh               por qué iTerm2 no aplica algo
├── colores/
│   ├── UMH-Elegante-Oscuro.itermcolors     tema principal
│   └── UMH-Elegante-Claro.itermcolors      tema para proyector/aula
├── datos/
│   ├── servidores-ejemplo.csv   inventario de ejemplo, listo para copiar
│   ├── servidores.csv           el tuyo (no se versiona)
│   └── maquina.txt              cómo se llama este ordenador (no se versiona)
├── ejemplos/
│   ├── UMH-Perfiles.json        lo que sale del inventario de ejemplo
│   └── umh.conf                 idem, para ~/.ssh/config.d/
└── MANUAL.md                    este documento
```

Los perfiles y la configuración SSH de tu inventario se generan en `perfiles/` y
`ssh/`, que tampoco se versionan: llevan tus direcciones, usuarios y claves.

Instalación rápida:

```bash
cd iterm2-umh
bash instalar-iterm2.sh -m "iMac despacho"   # fuente, temas, predeterminado
python3 generar_perfiles.py --instalar    # perfiles + ~/.ssh/config.d
python3 generar_claves.py --dry-run       # ver qué haría con las claves
```

El apartado 7 explica el inventario en CSV y los dos generadores, que son la
forma recomendada de trabajar a partir de unos pocos servidores.

---

## 1. Apariencia, color y tipografía

### 1.1 Tipografía

| Parámetro | Valor | Por qué |
|---|---|---|
| Fuente | `JetBrainsMono Nerd Font Mono` 14 pt | Monoespaciada estricta, `0`/`O` y `1`/`l`/`I` muy diferenciados, incluye los iconos Powerline/Nerd que usan `oh-my-zsh`, `eza`, `lazygit`… |
| Interlineado | 1.12 | Respira sin separar bloques; mejora la lectura de logs largos |
| Espaciado horizontal | 1.00 | Sin deformar la rejilla monoespaciada |
| Negrita / cursiva | activadas | El resaltado de sintaxis en `vim`/`bat` se aprovecha |
| Ligaduras | desactivadas | La variante *Mono* de Nerd Fonts no las incluye por diseño; si las quieres usa la variante sin «Mono» |
| Perfil de aula | 18 pt y tema claro | Legible desde el fondo del aula y en proyectores con poco contraste |

Instalación de la fuente:

```bash
brew install --cask font-jetbrains-mono-nerd-font
```

> **Importante.** iTerm2 guarda la fuente por su **nombre PostScript**, no por el nombre
> de familia. Si no coincide, iTerm2 cae silenciosamente a Monaco. Para comprobarlo:
>
> ```bash
> mdls -name com_apple_ats_name_postscript \
>   ~/Library/Fonts/JetBrainsMonoNerdFontMono-Regular.ttf
> ```
>
> El valor esperado es `JetBrainsMonoNFM-Regular`. El script de instalación hace esta
> comprobación y corrige el JSON automáticamente si tu versión de la fuente usa otro nombre.

### 1.2 Paleta «UMH Elegante Oscuro»

Fondo azul-carbón muy oscuro (`#11141A`) con texto gris cálido (`#D7DCE3`): contraste
alto pero sin el blanco puro sobre negro puro, que cansa en sesiones largas. Los 16
colores ANSI están desaturados de forma homogénea para que ninguno "salte" y todos
mantengan legibilidad sobre el fondo.

| Elemento | Color | Elemento | Color |
|---|---|---|---|
| Fondo | `#11141A` | Rojo / brillante | `#D4696A` / `#E68A8B` |
| Texto | `#D7DCE3` | Verde / brillante | `#86B38A` / `#A3CCA6` |
| Cursor (barra, parpadeo) | `#D8B06A` | Amarillo / brillante | `#D8B06A` / `#EDCB8A` |
| Selección | `#2E3950` | Azul / brillante | `#7FA5D9` / `#A0C0E8` |
| Enlaces | `#7FB8D9` | Magenta / brillante | `#B38AC4` / `#CBA8D8` |
| Negrita | `#EDF0F4` | Cian / brillante | `#6FB5B8` / `#92CDD0` |

La variante clara (`#FBFAF7` sobre `#23262B`) usa los mismos tonos oscurecidos para
mantener legibilidad con luz ambiente alta.

Importar a mano: doble clic en el `.itermcolors` → *Ajustes › Perfiles › Colores ›
Color Presets…* y elegir el preset. Los perfiles de este paquete ya traen los colores
incrustados, así que esto sólo hace falta si quieres aplicarlos a otros perfiles tuyos.

### 1.3 Ajustes globales de la aplicación (GUI)

Los perfiles no cubren los ajustes de la aplicación. Merece la pena tocar, en
*iTerm2 › Settings*:

- **Appearance › Theme: `Minimal`** y *Tab bar position: Top*. Elimina el cromado del
  título y deja que el color de pestaña de cada perfil domine la ventana — es lo que
  hace que se vea de un golpe en qué servidor estás.
- **Appearance › Dim inactive split panes** y *Show window number in title bar*.
- **General › Selection › Copy to pasteboard on selection**: seleccionar ya copia.
- **Profiles › Keys › Key Mappings › Presets… › `Natural Text Editing`**: habilita
  `⌥←`/`⌥→` por palabra y `⌘←`/`⌘→` a inicio/fin de línea, como en el resto de macOS.
  Aplícalo al perfil **Base** y lo heredan todos.
- **Advanced**: busca "pane" y activa *Dim text in inactive panes* si trabajas con
  muchos paneles.

### 1.4 Teclado y comodidad ya incluidos en los perfiles

| Ajuste | Valor | Efecto |
|---|---|---|
| `Option Key Sends` / `Right Option` | `Esc+` | `⌥b`/`⌥f` mueven por palabras en zsh/bash |
| Scrollback | 50 000 líneas | Historial amplio sin memoria ilimitada |
| Terminal type | `xterm-256color` | 256 colores en `vim`, `htop`, `tmux` |
| Campana | silenciada + aviso visual | Nada de pitidos en clase |
| Mouse reporting | activado | Scroll y clic dentro de `tmux`/`vim` |
| Cursor | barra vertical, parpadeante | Se localiza rápido en pantallas grandes |
| Ventana | 120 × 34 | Cabe un `ls -l` o un log de Apache sin cortar |

---

## 2. Perfiles

### 2.1 Por qué perfiles dinámicos (y no la GUI)

Un **perfil dinámico** es un simple archivo JSON en:

```
~/Library/Application Support/iTerm2/DynamicProfiles/
```

iTerm2 lo vigila y **recarga los cambios al instante**, sin reiniciar. Ventajas sobre
editar perfiles en la GUI:

- Versionable: el archivo puede ir a un repositorio Git con el resto de tus *dotfiles*.
- Reproducible: el mismo archivo te deja igual el ordenador del despacho y el portátil.
- Editable en masa: cambiar la fuente de los 7 perfiles es un `sed`, no 7 ventanas.
- Los perfiles dinámicos **no se pueden borrar por accidente** desde la GUI.

Reglas que conviene conocer:

1. Cada perfil necesita `Name` y `Guid` **único y estable** (los de este paquete se
   derivan del nombre con UUIDv5, así que se regeneran idénticos).
2. `"Dynamic Profile Parent Name"` crea **herencia**: el hijo sólo declara lo que cambia.
3. Los archivos se cargan por orden alfabético de nombre de archivo.
4. Si hay un error de sintaxis, el perfil no aparece y el motivo se registra en
   **Console.app** (busca "iTerm2").

### 2.2 Los perfiles que se generan

`generar_perfiles.py` produce un perfil padre y un hijo por cada fila incluida del
inventario. Con el inventario de ejemplo sale esto:

| Perfil | Comando | Color de pestaña | Distintivo | Atajo |
|---|---|---|---|---|
| **UMH · Base** | shell local (plantilla y predeterminado) | gris | — | — |
| UMH · servidor | `ssh servidor` | azul | `servidor` | `⌥⌘1` |
| UMH · servidor-web | `ssh servidor-web` | cian | `servidor · web` | `⌥⌘2` |
| LAB · equipo-lan | `ssh equipo-lan` | verde | `equipo · LAN` | `⌥⌘3` |
| LAB · equipo-wifi | `ssh equipo-wifi` | verde | `equipo · wifi` | `⌥⌘4` |
| LAB · equipo-otro-sistema | `ssh equipo-otro-sistema` | violeta | `otro sistema` | `⌥⌘5` |

El nombre del hijo es `GRUPO · nombre`, así que los perfiles de un mismo grupo quedan
juntos en la lista de iTerm2. El padre lleva la tipografía y el comportamiento; cada
hijo solo declara lo que cambia: ventana, color, distintivo, atajo, tema y comando.

El **distintivo** (*badge*) es el texto grande y semitransparente que iTerm2 dibuja
en la esquina de la sesión. Junto con el color de pestaña es la mejor defensa contra
el clásico «creía que estaba en mi portátil» justo antes de un `rm -rf`. Una fila con
`tema = aviso` añade además fondo rojizo, y con `confirmar = si` pide confirmación al
cerrar la sesión: la combinación habitual para un acceso de producción.

> El atajo se declara con `"Shortcut": "1"` y iTerm2 añade los modificadores `⌥⌘`.
> Si prefieres otra combinación, grábala en *Ajustes › Perfiles › Keys › Shortcut*.

### 2.3 Ejemplo: añadir un perfil nuevo

Para un servidor nuevo basta este bloque dentro de `"Profiles": [ … ]`:

```json
{
  "Name": "TALLER · plc-antiguo",
  "Guid": "pon-aqui-un-identificador-unico",
  "Dynamic Profile Parent Name": "UMH · Base",
  "Custom Command": "Yes",
  "Command": "ssh plc-antiguo",
  "Badge Text": "taller",
  "Badge Max Width": 0.3,
  "Use Tab Color": true,
  "Tab Color": {
    "Color Space": "sRGB",
    "Red Component": 0.48,
    "Green Component": 0.24,
    "Blue Component": 0.55,
    "Alpha Component": 1
  }
}
```

Guarda el archivo y el perfil aparece en *Perfiles* sin reiniciar iTerm2. Observa que
el comando es `ssh plc-antiguo`: el **alias** de `~/.ssh/config`, no la línea completa.
Así el usuario, el puerto y la clave se definen en un único sitio.

Truco inverso, para partir de algo que ya te gusta: configura un perfil en la GUI y
usa *Ajustes › Perfiles › Other Actions… › Save Profile as JSON*; obtienes todas las
claves válidas con sus valores reales y puedes quedarte sólo con las que te interesen.

### 2.4 Distribución de la ventana

Con todo esto, un arranque de trabajo típico es:

```
⌥⌘1   pestaña al servidor
⌘d    dividir el panel en vertical
⌥⌘2   pestaña a su raíz web
⌘⇧e   ver el historial de comandos (con shell integration)
```

Si siempre abres la misma composición, créala y guárdala con
*Window › Save Window Arrangement* (`⌘⇧S`), y en *Settings › General › Startup*
elige abrirla al iniciar.

---

## 3. SSH con claves ("certificados")

### 3.1 Aclaración de términos

Lo que se genera con `ssh-keygen -t ed25519` es un **par de claves** (privada +
pública), no un certificado. En la práctica a esto se le llama «acceso por
certificado» y es el 99 % de los casos. Hay además **certificados SSH de verdad**,
firmados por una CA, que se tratan en el apartado 3.7.

Sobre las dos primeras líneas de tu procedimiento habitual:

```bash
apt-get install ca-certificates     # Debian/Ubuntu
update-ca-certificates
```

Esos paquetes gestionan las **CA de TLS/HTTPS** (lo que usan `curl`, `wget` o Apache),
y no intervienen en la autenticación SSH. En macOS no aplican: el almacén de confianza
es el Llavero del sistema. Útiles en los servidores Linux, innecesarias en macOS para
este propósito.

### 3.2 Generar las claves

```bash
# Clave moderna recomendada (rápida, corta, segura)
ssh-keygen -t ed25519 -a 100 -C "imac-usuario-202611" -f ~/.ssh/id_ed25519_umh

# Sólo si algún equipo antiguo no admite Ed25519
ssh-keygen -t rsa -b 4096 -a 100 -C "imac-usuario-rsa" -f ~/.ssh/id_rsa_umh
```

| Opción | Para qué |
|---|---|
| `-t ed25519` | Curva elíptica Ed25519: clave de 68 bytes, verificación muy rápida |
| `-a 100` | 100 rondas de KDF al cifrar la clave privada: encarece un ataque por fuerza bruta sobre la passphrase |
| `-C "…"` | Comentario; identifica **de qué máquina** es la clave cuando leas `authorized_keys` en el servidor dentro de dos años |
| `-f <ruta>` | Un archivo por propósito, en lugar de un `id_ed25519` genérico. Facilita revocar sólo una |

**Pon passphrase.** Con el Llavero de macOS sólo la escribes una vez (3.4), así que no
hay pérdida de comodidad y la clave robada no sirve de nada.

### 3.3 Copiar la clave pública al servidor

```bash
ssh-copy-id -i ~/.ssh/id_ed25519_umh.pub usuario@servidor.umh.es
```

Es la última vez que escribes la contraseña. Si `ssh-copy-id` no estuviese disponible:

```bash
ssh usuario@servidor.umh.es \
  'umask 077; mkdir -p ~/.ssh; cat >> ~/.ssh/authorized_keys' \
  < ~/.ssh/id_ed25519_umh.pub
```

Verificación inmediata — si pide contraseña, la clave no está activa:

```bash
ssh -o PasswordAuthentication=no usuario@servidor.umh.es 'hostname; whoami'
```

### 3.4 Agente y Llavero de macOS

```bash
ssh-add --apple-use-keychain ~/.ssh/id_ed25519_umh   # guarda la passphrase
ssh-add -l                                           # claves cargadas ahora
```

Con `AddKeysToAgent yes` y `UseKeychain yes` en `~/.ssh/config` (ya incluido), macOS
recarga la clave sola tras cada reinicio y no vuelve a preguntar.

### 3.5 `~/.ssh/config`: el archivo que ahorra más tiempo

Extracto de lo que genera (`ssh/umh.conf`):

```ssh-config
Host servidor
    HostName        servidor.umh.es
    User            usuario
    IdentityFile    ~/.ssh/id_ed25519_umh
    IdentitiesOnly  yes

Host *
    AddKeysToAgent          yes
    UseKeychain             yes
    ServerAliveInterval     60
    ServerAliveCountMax     3
    ControlMaster           auto
    ControlPath             ~/.ssh/cm/%r@%h:%p
    ControlPersist          10m
    HashKnownHosts          yes
```

Con eso, `ssh usuario@servidor.umh.es -i …` se convierte en `ssh servidor`, y lo mismo vale para
`scp`, `rsync`, `sftp` y los perfiles de iTerm2.

| Opción | Qué resuelve |
|---|---|
| `IdentitiesOnly yes` | Ofrece **sólo** la clave indicada. Sin esto, con varias claves el servidor puede rechazarte por exceso de intentos (`Too many authentication failures`) |
| `ServerAliveInterval 60` | Manda un latido cada minuto: la sesión no muere al cambiar de red o volver de suspensión |
| `ControlMaster` + `ControlPath` + `ControlPersist` | Multiplexado: la 2.ª y 3.ª sesión reutilizan la conexión TCP ya abierta y entran de inmediato. Requiere `mkdir -p ~/.ssh/cm && chmod 700 ~/.ssh/cm` |
| `ProxyJump servidor` | Entrar a una máquina interna atravesando otra, sin `ssh` anidados |
| `PubkeyAcceptedAlgorithms +ssh-rsa` | Hablar con equipos antiguos (PLC, switches) que sólo firman con RSA-SHA1 |
| `HashKnownHosts yes` | `known_hosts` no revela en claro la lista de servidores a los que accedes |

**El orden importa:** SSH aplica el **primer** valor que encuentra para cada opción.
Los `Host` específicos van arriba y `Host *` al final.

Permisos obligatorios (SSH se niega a trabajar si están abiertos):

```bash
chmod 700 ~/.ssh
chmod 600 ~/.ssh/config ~/.ssh/id_ed25519_umh
chmod 644 ~/.ssh/id_ed25519_umh.pub
```

### 3.6 Lado servidor

En el servidor, lo que rompe el acceso por clave casi siempre son los permisos:

```bash
chmod 700 ~/.ssh
chmod 600 ~/.ssh/authorized_keys
```

Endurecer `sshd` una vez comprobado que la clave funciona (`/etc/ssh/sshd_config`):

```ssh-config
PubkeyAuthentication yes
PasswordAuthentication no        # ¡sólo tras verificar tu acceso por clave!
PermitRootLogin prohibit-password
```

```bash
sshd -t && systemctl reload sshd   # -t valida antes de recargar
```

> Deja **una segunda sesión abierta** mientras recargas `sshd`. Si algo va mal, aún
> tienes una terminal dentro para revertir. En un servidor al que
> accedes por red externa, es la diferencia entre un susto y un viaje al CPD.

### 3.7 Certificados SSH reales (opcional, avanzado)

Interesante si gestionas varias máquinas: firmas tu clave con una CA propia y los
servidores confían en la CA, de modo que **no hay que tocar `authorized_keys`** en
cada servidor nuevo, y los accesos **caducan solos**.

```bash
# 1) Crear la CA (en un sitio seguro, idealmente fuera del equipo de trabajo)
ssh-keygen -t ed25519 -f ~/.ssh/ca_umh -C "CA SSH UMH"

# 2) Firmar tu clave pública: identidad "usuario", válida 52 semanas
ssh-keygen -s ~/.ssh/ca_umh -I usuario -n usuario -V +52w \
           ~/.ssh/id_ed25519_umh.pub
#    -> genera ~/.ssh/id_ed25519_umh-cert.pub

# 3) Inspeccionar lo firmado
ssh-keygen -L -f ~/.ssh/id_ed25519_umh-cert.pub
```

En el servidor, copiar `ca_umh.pub` y declararlo en `/etc/ssh/sshd_config`:

```ssh-config
TrustedUserCAKeys /etc/ssh/ca_umh.pub
RevokedKeys       /etc/ssh/revoked_keys
```

Y en el cliente, `CertificateFile ~/.ssh/id_ed25519_umh-cert.pub` (ya aparece de
ejemplo en la plantilla de `ssh/umh.conf`).

### 3.8 Diagnóstico

```bash
ssh -v servidor       # qué clave ofrece y por qué se rechaza
ssh -vvv servidor     # detalle completo
ssh-add -l            # ¿está la clave en el agente?
ssh-keygen -lf ~/.ssh/id_ed25519_umh.pub   # huella, para comparar con el servidor
ssh-keygen -R servidor.umh.es                 # olvidar una clave de host cambiada
```

| Síntoma | Causa habitual |
|---|---|
| Sigue pidiendo contraseña | Permisos en `~/.ssh` o `authorized_keys` del servidor, o `IdentityFile` equivocado |
| `Too many authentication failures` | Falta `IdentitiesOnly yes` |
| `REMOTE HOST IDENTIFICATION HAS CHANGED` | El servidor se reinstaló: `ssh-keygen -R <host>` tras confirmar que es legítimo |
| `Permission denied (publickey)` con `PasswordAuthentication no` | La clave no llegó al servidor; entra desde otra sesión ya abierta |
| `Agent admitted failure to sign` | La clave no está en el agente: `ssh-add --apple-use-keychain …` |

---

## 4. Complementos que encajan bien

**Shell integration de iTerm2** — marcas de prompt (`⌘↑`/`⌘↓` salta entre comandos),
historial de comandos y descarga de archivos con clic derecho:

```bash
curl -L https://iterm2.com/shell_integration/zsh \
  -o ~/.iterm2_shell_integration.zsh
echo 'source ~/.iterm2_shell_integration.zsh' >> ~/.zshrc
```

Para que funcione también en los servidores, instálalo allí igualmente (iTerm2 3.5+
incluye `it2ssh`, que lo lleva consigo al conectar).

**Atajos que más se usan**

| Atajo | Acción | Atajo | Acción |
|---|---|---|---|
| `⌘d` / `⌘⇧d` | Dividir vertical / horizontal | `⌘⇧h` | Historial del portapapeles |
| `⌘⌥←→` | Moverse entre paneles | `⌘⇧e` | Historial de comandos |
| `⌘⇧Enter` | Maximizar el panel | `⌘f` | Buscar (con `⌥Enter` para pegar lo hallado) |
| `⌘;` | Autocompletar desde el historial | `⌘⌥b` | Reproducción instantánea (*instant replay*) |

---

## 5. Mantenimiento

```bash
# Editar perfiles (se recargan al guardar)
open -a TextEdit "$HOME/Library/Application Support/iTerm2/DynamicProfiles/UMH-Perfiles.json"

# Cambiar la fuente de todos los perfiles de golpe
sed -i '' 's/JetBrainsMonoNFM-Regular 14/JetBrainsMonoNFM-Regular 15/g' \
  "$HOME/Library/Application Support/iTerm2/DynamicProfiles/UMH-Perfiles.json"

# Copia de seguridad de los ajustes globales de iTerm2
cp ~/Library/Preferences/com.googlecode.iterm2.plist ~/Backups/
```

Recomendación: guarda `iterm2-umh/` completo en un repositorio y enlaza el JSON en
lugar de copiarlo, para tener una sola fuente de verdad:

```bash
ln -sf ~/repos/dotfiles/iterm2-umh/perfiles/UMH-Perfiles.json \
  "$HOME/Library/Application Support/iTerm2/DynamicProfiles/UMH-Perfiles.json"
```

---

## 6. Si la fuente o el tamaño de ventana no se aplican

```bash
bash diagnostico.sh
```

Las cuatro causas, por orden de frecuencia:

**1. iTerm2 sigue abriendo el perfil antiguo.** Si ves `80×25` y `Monaco 12`, son los
valores de fábrica: la ventana no usa ningún perfil `UMH`. Un perfil **dinámico no
puede marcarse como predeterminado desde su JSON**; el predeterminado vive en los
ajustes de la aplicación. Dos formas de arreglarlo:

```bash
osascript -e 'quit app "iTerm"'; sleep 3      # imprescindible: cerrar iTerm2
defaults write com.googlecode.iterm2 "Default Bookmark Guid" \
  -string "415d01c5-71c8-5639-bd7e-0d90e99b4a0f"   # UMH · Base
```

O por GUI: *Ajustes › Perfiles*, seleccionar **UMH · Base** ›
*Other Actions… › Set as Default*.

**2b. El perfil dice `"Normal Font": "null 14"`.** Le ocurrió al instalador en su
primera versión: consultaba `mdls` justo después de instalar la fuente, cuando Spotlight
todavía no la había indexado, y `mdls` devuelve `(null)`. Reparación directa:

```bash
DYN="$HOME/Library/Application Support/iTerm2/DynamicProfiles/UMH-Perfiles.json"
sed -i '' 's/"null \([0-9]\{1,2\}\)"/"JetBrainsMonoNFM-Regular \1"/g' "$DYN"
grep -n '"Normal Font"' "$DYN"
```

**2. El nombre PostScript de la fuente no coincide.** iTerm2 guarda la tipografía por
su nombre PostScript; si no existe, **cae a Monaco sin avisar**. Comprueba el real y
sustitúyelo:

```bash
mdls -raw -name com_apple_ats_name_postscript \
  ~/Library/Fonts/JetBrainsMonoNerdFontMono-Regular.ttf

sed -i '' 's/JetBrainsMonoNFM-Regular/<NOMBRE_REAL>/g' \
  "$HOME/Library/Application Support/iTerm2/DynamicProfiles/UMH-Perfiles.json"
```

El valor debe quedar como `"Normal Font": "<NOMBRE_REAL> 14"` — nombre, espacio,
tamaño, en la misma cadena.

**3. `Columns`/`Rows` sólo se aplican a ventanas nuevas.** `⌘T` (pestaña nueva) hereda
el tamaño de la ventana actual; hay que usar `⌘N`. En pantalla completa o con la
ventana maximizada se ignoran siempre.

**4. Restauración de ventanas.** Si *Settings › General › Startup › Window restoration
policy* restaura una composición, o macOS restaura la geometría anterior, el tamaño del
perfil se descarta:

```bash
defaults write -g NSQuitAlwaysKeepsWindows -bool false
```

> Los perfiles dinámicos **son de sólo lectura en la GUI**: si cambias la fuente o el
> tamaño desde *Ajustes › Perfiles*, iTerm2 lo descarta al recargar el archivo. Edita
> siempre el JSON. Si prefieres un perfil editable a mano, impórtalo como perfil normal
> con *Other Actions… › Import JSON Profiles* y bórralo de `DynamicProfiles/`.

---

## 7. El inventario en CSV y los dos generadores

A partir de cierto número de servidores no tiene sentido editar el JSON a mano.
Los servidores viven en una hoja de cálculo (pestañas **Servidores** y **Leyenda**),
se exporta la pestaña `Servidores` como CSV, y dos scripts hacen el resto.

```
datos/servidores.csv            el inventario exportado de tu hoja
umh_inventario.py               lectura y validación (lo usan los dos scripts)
generar_perfiles.py             -> perfiles/UMH-Perfiles.json  +  ssh/umh.conf
generar_claves.py               -> claves, Llavero y ssh-copy-id
```

```bash
python3 generar_perfiles.py                   # genera y valida, sin instalar
python3 generar_perfiles.py --instalar        # ...y lo pone en su sitio
python3 generar_claves.py --dry-run           # qué haría, sin tocar nada
python3 generar_claves.py --solo equipo-lan   # una sola máquina
python3 generar_claves.py --grupo LAB         # un grupo entero
```

### 7.1 Las columnas se leen por su nombre

Cualquier hoja con esta estructura vale: las columnas se buscan **por el nombre de
la cabecera**, no por su posición, así que puedes reordenarlas, añadir otras —se
ignoran, con un aviso— u omitir las opcionales. Solo `nombre` y `direccion` son
obligatorias. La columna `incluir` hace de comentario: las filas con `no` no generan
nada. La leyenda completa está en la pestaña **Leyenda** de la hoja.

### 7.2 Valida antes de escribir

`generar_perfiles.py` revisa el lote completo y no escribe nada si hay errores:
nombres o atajos repetidos, un `salto` que apunta a una fila que no existe o está
excluida, una `clave` usada con dos `tipo_clave` distintos, valores no admitidos en
`tema`, `color` o `ventana`, obligatorios en blanco. Avisa, sin bloquear, de dos
dos filas que apunten al mismo `usuario@dirección:puerto` y de una IP compartida por
filas con distinto `alias_host` y alguna sin ninguno.

### 7.3 Lo que genera

**`perfiles/UMH-Perfiles.json`**: el perfil `UMH · Base` con la tipografía y el
comportamiento, y un hijo por fila llamado `GRUPO · nombre`, que solo declara lo que
cambia (ventana, color de pestaña, distintivo, atajo, tema, comando). Al final, fuera
del array `Profiles`, una clave `_PLANTILLA` con un bloque listo para copiar: JSON no
admite comentarios, y una entrada dentro de `Profiles` aparecería como un perfil
fantasma, mientras que iTerm2 ignora las claves que no conoce.

> **No renombres `UMH · Base`.** Su identificador se deriva del nombre, y es el que
> iTerm2 tiene guardado como perfil predeterminado: si cambia el nombre, cambia el
> GUID y vuelves a abrir ventanas con el perfil de fábrica.

**`ssh/umh.conf`**, que se instala en `~/.ssh/config.d/umh.conf`. Tu `~/.ssh/config`
no se sobrescribe: solo se le añade, al principio, `Include config.d/*.conf`. Al
principio porque SSH se queda con el **primer** valor de cada opción. El archivo
generado lleva su propio bloque `Host plantilla` comentado y, al final, el `Host *`
de opciones comunes.

De cada fila salen las opciones que le corresponden: `IdentityFile` con
`IdentitiesOnly`, `Port` si no es el 22, `ProxyJump` para `salto`,
`PubkeyAcceptedAlgorithms +ssh-rsa` para los equipos antiguos, y para `comando`
un `RequestTTY yes` con `RemoteCommand <orden> && exec $SHELL -l`. Esto último va en
el alias de esa fila y no en el de la máquina, así que `scp` y `rsync` siguen
funcionando si usas el alias sin `comando`.

El archivo empieza por `IgnoreUnknown UseKeychain,PubkeyAcceptedAlgorithms,PubkeyAcceptedKeyTypes`,
lo que lo hace válido también en Linux y en un OpenSSH antiguo: `UseKeychain` solo
existe en el de Apple, y sin esa línea `ssh` aborta con `Bad configuration option`
para cualquier host. Tiene que ir al principio, porque `IgnoreUnknown` no se aplica a
las opciones desconocidas que aparezcan antes que él.

Con `alias_host` se escriben `HostKeyAlias` y `CheckHostIP no`. Es lo que permite que
la misma máquina por LAN y por WiFi comparta una sola huella en `known_hosts`, y que
dos sistemas en arranque dual —o dos máquinas distintas con la misma IP en dos
redes— no se pisen las huellas entre sí. Cada sistema operativo tiene sus propias
claves de host: un `alias_host` compartido entre dos de ellos produce el aviso
`REMOTE HOST IDENTIFICATION HAS CHANGED` en cada cambio de arranque.

### 7.4 Las claves

`generar_claves.py` crea **una clave por cada valor distinto** de la columna `clave`
y después la copia **una vez por cada fila** que la use. Así una misma clave sirve
para varios usuarios del mismo servidor (dos cuentas distintas) o para varias
máquinas. Si el `config` ya está instalado usa los alias, con lo que hereda el puerto,
el usuario y los saltos; si no, cae a `usuario@dirección` y salta las filas que
necesiten `ProxyJump`. Al final comprueba cada acceso con
`ssh -o PasswordAuthentication=no` y resume qué entró sin contraseña.

Los filtros `--solo` y `--grupo` están sobre todo para el arranque dual: cada sistema
tiene su propio `authorized_keys`, así que la pública hay que copiarla con ese sistema
arrancado. Un fallo en esas máquinas suele significar solo que ahora está arrancado el
otro sistema.

### 7.5 El nombre de esta máquina

`instalar-iterm2.sh` pregunta cómo llamas al ordenador en el que lo ejecutas —o lo
tomas de `-m "iMac despacho"`— y lo guarda en `datos/maquina.txt`. Propone el nombre
que macOS ya tiene configurado (`scutil --get ComputerName`). Los dos generadores lo
leen de ahí y lo usan para dos cosas:

- **Distintivo de las sesiones locales.** Va en el perfil `UMH · Base`, que es el
  shell local. No lo heredan los perfiles de servidor, porque cada uno declara su
  propio distintivo. Así una ventana local se distingue de un `ssh` de un vistazo.
- **Comentario de las claves SSH.** `ssh-keygen -C "id_ed25519_lab iMac despacho
  2026-11"`. Ese comentario viaja con la pública al `authorized_keys` del servidor,
  y es lo único que te dirá, dentro de dos años, de qué ordenador salió cada línea y
  cuál puedes borrar sin miedo.

Para cambiarlo, vuelve a ejecutar el instalador con `-m`, o edita `datos/maquina.txt`
y regenera los perfiles. El archivo no se versiona: cada ordenador tiene el suyo, y es
justo lo que distingue al del despacho del portátil cuando los dos usan este repo.

### 7.6 Copias de seguridad, y por qué no van en DynamicProfiles

**iTerm2 carga todos los archivos de `~/Library/Application Support/iTerm2/DynamicProfiles/`**,
sea cual sea su extensión. Una copia de seguridad dejada ahí se carga como un juego de
perfiles más, con los mismos GUID y los mismos nombres que el original, y iTerm2 avisa
de cada choque al abrir ventana. Peor: un perfil que creías borrado sigue vivo, y si es
el predeterminado, sigue siendo el que abre `⌘N`.

Por eso las copias van a `~/.iterm2-umh-copias/`, fuera de esa carpeta. Si tienes
copias antiguas dentro, `instalar-iterm2.sh` las aparta solo, y avisa (sin tocarlos) de
cualquier otro archivo que encuentre ahí, que puede ser de otra herramienta.

Para mirarlo a mano:

```bash
ls -la ~/Library/Application\ Support/iTerm2/DynamicProfiles/
```

Solo debería haber `UMH-Perfiles.json`.

### 7.7 El ciclo de trabajo

```bash
# 1. editar la hoja y exportar la pestaña Servidores como CSV
#    (dejarlo en datos/servidores.csv, o pasarlo con --csv)
python3 generar_perfiles.py                 # revisar avisos y resumen
python3 generar_perfiles.py --instalar       # iTerm2 recarga al instante
python3 generar_claves.py --solo nuevo-host  # solo lo que falte
ssh -G nuevo-host | head -5                          # comprobar lo que resuelve SSH
```

---

*Rafael Puerto Manchón · Departamento de Ingeniería de Sistemas y Automática ·
Universidad Miguel Hernández de Elche · r.puerto@umh.es*

*Generado con IA · Revisado por el autor*
