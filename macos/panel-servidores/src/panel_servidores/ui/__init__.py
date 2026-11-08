"""Interfaz gráfica (PySide6/Qt 6) del Panel de Servidores.

Regla de oro de este paquete: **la interfaz no contiene lógica de negocio**. Cada botón llama a
una función del paquete ``nucleo`` (que no sabe nada de Qt) dentro de un hilo de trabajo y
muestra el resultado. Así la interfaz se puede rehacer o automatizar sin tocar nada del
funcionamiento, y el núcleo se prueba sin abrir ventanas.

Mapa de módulos
---------------
hilos            Ejecución en segundo plano (``Trabajo``) y vuelta segura al hilo de la interfaz.
puente           Diálogos que contestan a las preguntas del núcleo (contraseñas, huellas…).
contexto         Estado compartido: perfiles, conexiones abiertas, askpass, registro de actividad.
widgets          Piezas reutilizables: consola ANSI, barra de tarea, tablas de datos.
estilo           Hoja de estilo y tipografías.
dialogo_*        Ventanas modales (servidor, preferencias, informe de varios servidores…).
paginas/*        Una pestaña por función: Resumen, Informe, Servicio, Instalador, Claves, Aplicaciones.
ventana_principal  Lista de servidores + pestañas + consola de actividad + menús.
app              Arranque: QApplication, askpass interno, ventana principal.
"""
