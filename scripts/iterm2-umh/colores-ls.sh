# colores-ls.sh · ejecutables en ROJO en la salida de «ls» (zsh y bash)
#
# Se carga desde ~/.zshrc (instalar-iterm2.sh lo hace si respondes «s») o,
# en un servidor Linux, desde ~/.bashrc:
#     ssh SERVIDOR 'cat >> ~/.bashrc' < colores-ls.sh
#
# Para cambiar el color, edita solo las dos líneas marcadas con «<<».

# macOS / BSD (ls -G). Pares «letra de texto + letra de fondo», en este orden:
#   directorio, enlace, socket, tubería, EJECUTABLE, bloque, carácter,
#   setuid, setgid, dir. con sticky, dir. escribible.
# Letras: a negro, b rojo, c verde, d marrón, e azul, f magenta, g cian,
# h gris claro, x por defecto (en mayúscula, negrita).
export CLICOLOR=1
export LSCOLORS="exfxcxdxbxegedabagacad"    # << ejecutable = «bx» (rojo)

# GNU / Linux (ls --color), también con coreutils instalado con Homebrew.
# Se parte de los colores por defecto de dircolors si existen y se añade
# «ex» al final: en LS_COLORS la última entrada de cada tipo es la que vale.
if [ -z "${LS_COLORS:-}" ] && command -v dircolors >/dev/null 2>&1; then
  eval "$(dircolors -b)"
fi
export LS_COLORS="${LS_COLORS:+$LS_COLORS:}ex=01;31"    # << 01 = negrita, 31 = rojo
