"""Núcleo de la aplicación: lógica de negocio SIN dependencias de Qt.

Todo lo que hay en este paquete se puede importar, ejecutar y probar desde una terminal
(``pytest``), sin abrir ninguna ventana. La interfaz (paquete ``ui``) solo orquesta estas
piezas y muestra sus resultados.

Mapa de módulos
---------------
modelos      Dataclasses compartidas (Perfil, Resultado, Interaccion…).
almacen      Persistencia de perfiles y ajustes (JSON en Application Support).
secretos     Contraseñas / frases: preguntar, llavero de macOS o variable de entorno.
askpass      Puente ssh ↔ interfaz: responde a las preguntas de ssh (contraseña, 2FA, huella).
ssh          Conexión SSH (todas las variantes de autenticación, multiplexado, streaming).
remoto       Constructores de comandos POSIX que se ejecutan en el servidor.
claves       Claves SSH locales (generar, listar, agente) y authorized_keys remoto.
colector     Informe de TeleMet Collector, servicio systemd y comprobaciones.
instalador   Opciones y ejecución de ``instalar-todo.sh`` / ``instalar-todo-isa.sh``.
github       API pública de GitHub (repos y carpetas) y descarga de scripts.
recursos     Acceso a los scripts incluidos (o a una carpeta personalizada).
ansi         Conversión de secuencias ANSI a HTML para mostrar el informe en color.
"""
