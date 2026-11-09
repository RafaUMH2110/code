"""Pestaña «Instalador»: ``instalar-todo.sh`` / ``instalar-todo-isa.sh`` con formulario y progreso.

Cuatro subpestañas:

* **Configuración** — todas las opciones del script con validación y vista previa del comando.
* **Repositorios** — qué clonar: selección guardada, todos, una lista o todos menos algunos, con un
  árbol de repos y carpetas de GitHub (el menú numerado del script, pero visual).
* **Ejecución** — los 6 pasos con su estado, el registro en vivo y el resumen final.
* **Mantenimiento** — registro del servidor, selección guardada, cron y copias de seguridad.

La aplicación sube el script al servidor y lo ejecuta allí (ver ``nucleo/instalador.py``).
"""

from __future__ import annotations


from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
                               QPlainTextEdit, QPushButton, QRadioButton, QButtonGroup, QScrollArea, QSplitter,
                               QTabWidget, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from ...nucleo import github, instalador
from ...nucleo.instalador import (OpcionesInstalador, PASOS, SELECCION_EXCLUIR, SELECCION_GUARDADA, SELECCION_LISTA,
                                  SELECCION_TODOS)
from ...nucleo.modelos import VARIANTE_ISA, VARIANTE_LOCAL
from ...nucleo.recursos import Recursos
from .. import estilo, hilos
from ..widgets import ConsolaAnsi, VistaComando, ajustar_arbol, copiar, preparar_arbol
from .base import PaginaBase

CRONS = [("(sin cron)", ""), ("Cada noche a las 03:00", "0 3 * * *"), ("Cada hora", "0 * * * *"),
         ("Cada 6 horas", "0 */6 * * *"), ("Lunes a las 07:00", "0 7 * * 1")]
MODOS = [("web — publica solo los ficheros web (recomendado)", "web"), ("html — solo los .html", "html"),
         ("todo — todo el contenido del repo", "todo")]
PLACEHOLDER = "__cargando__"


class PaginaInstalador(PaginaBase):
    titulo = "Instalador"

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        self._pasos: list = []
        self._opciones_cargando = False
        self._construido = False          # evita reaccionar a señales mientras se crea la interfaz
        self._repos_sel_pendiente: set = set()
        self.pestanas = QTabWidget()
        self.pestanas.addTab(self._construir_config(), "Configuración")
        self.pestanas.addTab(self._construir_repos(), "Repositorios")
        self.pestanas.addTab(self._construir_ejecucion(), "Ejecución")
        self.pestanas.addTab(self._construir_mantenimiento(), "Mantenimiento")
        self.raiz.addWidget(self.pestanas, 1)

        # --- barra inferior común
        self.vista_previa = VistaComando()
        self.b_copiar = QPushButton("Copiar")
        self.b_guardar = QPushButton("Guardar como predeterminado")
        self.b_instalar = QPushButton("Instalar / actualizar")
        self.b_instalar.setDefault(True)
        fila = QHBoxLayout()
        fila.addWidget(QLabel("Equivale a:"))
        fila.addWidget(self.vista_previa, 1)
        fila.addWidget(self.b_copiar)
        self.raiz.addLayout(fila)
        fila2 = QHBoxLayout()
        fila2.addWidget(self.barra, 1)
        fila2.addWidget(self.b_guardar)
        fila2.addWidget(self.b_instalar)
        self.raiz.addLayout(fila2)

        self.b_copiar.clicked.connect(lambda: copiar(self.vista_previa.text()))
        self.b_guardar.clicked.connect(self.guardar_predeterminado)
        self.b_instalar.clicked.connect(lambda: self.instalar())
        self._construido = True
        self.perfil_cambiado()

    # ====================================================================== construcción de la interfaz
    def _construir_config(self) -> QWidget:
        cont = QWidget()
        capa = QVBoxLayout(cont)

        g1 = QGroupBox("Origen y destino")
        f1 = QFormLayout(g1)
        self.variante = QComboBox()
        self.variante.addItem("Servidor local (instalar-todo.sh · /var/www/html)", VARIANTE_LOCAL)
        self.variante.addItem("Producción isa.umh.es (instalar-todo-isa.sh · /var/www/htdocs)", VARIANTE_ISA)
        self.usuario_gh = QLineEdit()
        self.origen = QLineEdit()
        self.origen.setPlaceholderText("~/RafaUMH2110  (carpeta de repos clonados, en el servidor)")
        self.destino = QLineEdit()
        self.docroot = QLineEdit()
        self.dir_script = QLineEdit()
        f1.addRow("Script:", self.variante)
        f1.addRow("Usuario de GitHub (-u):", self.usuario_gh)
        f1.addRow("Carpeta de repos (-o):", self.origen)
        f1.addRow("Destino web (-d):", self.destino)
        f1.addRow("DocumentRoot de Apache (--docroot):", self.docroot)
        f1.addRow("Dejar el instalador en:", self.dir_script)
        capa.addWidget(g1)

        g2 = QGroupBox("Qué se publica")
        f2 = QFormLayout(g2)
        self.modo = QComboBox()
        for texto, valor in MODOS:
            self.modo.addItem(texto, valor)
        self.sin_indice = QCheckBox("No generar el portal (index.html / apps.json) (--sin-indice)")
        self.forzar = QCheckBox("Sobrescribir un destino con contenido ajeno, con copia previa (--forzar)")
        f2.addRow("Modo (--modo):", self.modo)
        f2.addRow("", self.sin_indice)
        f2.addRow("", self.forzar)
        capa.addWidget(g2)

        g3 = QGroupBox("Colector de telemetría y cron")
        f3 = QFormLayout(g3)
        self.colector = QCheckBox("Instalar el servicio del colector (--colector)")
        self.estacion = QLineEdit()
        self.estacion.setPlaceholderText("Station ID de Weather Underground (opcional)")
        self.clave_api = QLineEdit()
        self.clave_api.setEchoMode(QLineEdit.EchoMode.Password)
        self.clave_api.setPlaceholderText("API Key (opcional; nunca se guarda ni va en la línea de comandos)")
        self.cron_preset = QComboBox()
        for texto, valor in CRONS:
            self.cron_preset.addItem(texto, valor)
        self.cron = QLineEdit()
        self.cron.setPlaceholderText("min hora día mes día-semana, p. ej. 0 3 * * *")
        f3.addRow("", self.colector)
        f3.addRow("Station ID:", self.estacion)
        f3.addRow("API Key:", self.clave_api)
        f3.addRow("Actualizar con cron:", self.cron_preset)
        f3.addRow("Expresión (--cron):", self.cron)
        capa.addWidget(g3)

        self.g_isa = QGroupBox("Solo producción (isa)")
        f4 = QFormLayout(self.g_isa)
        self.url = QLineEdit()
        self.url.setPlaceholderText("https://isa.umh.es")
        self.entrada_raiz = QCheckBox("Añadir también una entrada en la raíz del sitio (--entrada-raiz)")
        self.json_dir = QLineEdit()
        f4.addRow("URL pública (--url):", self.url)
        f4.addRow("", self.entrada_raiz)
        f4.addRow("Carpeta del JSON (--json-dir):", self.json_dir)
        capa.addWidget(self.g_isa)
        capa.addStretch(1)

        for w in (self.usuario_gh, self.origen, self.destino, self.docroot, self.dir_script, self.cron, self.url,
                  self.json_dir):
            w.textChanged.connect(self._cambiado)
        for w in (self.sin_indice, self.forzar, self.colector, self.entrada_raiz):
            w.toggled.connect(self._cambiado)
        self.variante.currentIndexChanged.connect(self._cambiado)
        self.modo.currentIndexChanged.connect(self._cambiado)
        self.cron_preset.currentIndexChanged.connect(self._preset_cron)
        self.colector.toggled.connect(lambda v: (self.estacion.setEnabled(v), self.clave_api.setEnabled(v)))

        marco = QScrollArea()
        marco.setWidgetResizable(True)
        marco.setWidget(cont)
        return marco

    def _construir_repos(self) -> QWidget:
        cont = QWidget()
        capa = QVBoxLayout(cont)
        fila = QHBoxLayout()
        self.grupo_sel = QButtonGroup(self)
        self.radios: dict = {}
        for clave, texto in ((SELECCION_GUARDADA, "Usar la selección guardada en el servidor"),
                             (SELECCION_TODOS, "Todos los repos"),
                             (SELECCION_LISTA, "Solo los marcados"),
                             (SELECCION_EXCLUIR, "Todos menos los marcados")):
            r = QRadioButton(texto)
            self.grupo_sel.addButton(r)
            self.radios[clave] = r
            fila.addWidget(r)
            r.toggled.connect(self._cambiado)
        self.radios[SELECCION_GUARDADA].setChecked(True)
        fila.addStretch(1)
        capa.addLayout(fila)

        div = QSplitter()
        izq = QWidget()
        li = QVBoxLayout(izq)
        self.arbol = QTreeWidget()
        self.arbol.setHeaderLabels(["Repositorio / carpeta", "Lenguaje", "KB"])
        preparar_arbol(self.arbol)
        self.arbol.itemChanged.connect(self._cambiado)
        self.arbol.itemExpanded.connect(self._expandido)
        fila_b = QHBoxLayout()
        self.b_cargar = QPushButton("Cargar repos de GitHub")
        self.b_marcar = QPushButton("Marcar todos")
        self.b_desmarcar = QPushButton("Desmarcar")
        for b in (self.b_cargar, self.b_marcar, self.b_desmarcar):
            fila_b.addWidget(b)
        fila_b.addStretch(1)
        li.addWidget(QLabel("Despliega un repo para elegir carpetas concretas (como «repo/carpeta»). "
                            "Los repos archivados no aparecen."))
        li.addWidget(self.arbol, 1)
        li.addLayout(fila_b)
        der = QWidget()
        ld = QVBoxLayout(der)
        ld.addWidget(QLabel("Selección guardada en el servidor (ORIGEN/.seleccion):"))
        self.sel_servidor = QPlainTextEdit()
        self.sel_servidor.setReadOnly(True)
        self.sel_servidor.setFont(estilo.fuente_mono())
        fila_b2 = QHBoxLayout()
        self.b_leer_sel = QPushButton("Leer del servidor")
        self.b_listar = QPushButton("Listar con el script (--listar)")
        fila_b2.addWidget(self.b_leer_sel)
        fila_b2.addWidget(self.b_listar)
        ld.addWidget(self.sel_servidor, 1)
        ld.addLayout(fila_b2)
        div.addWidget(izq)
        div.addWidget(der)
        div.setSizes([600, 380])
        capa.addWidget(div, 1)
        self.b_cargar.clicked.connect(self.cargar_repos)
        self.b_marcar.clicked.connect(lambda: self._marcar_todos(True))
        self.b_desmarcar.clicked.connect(lambda: self._marcar_todos(False))
        self.b_leer_sel.clicked.connect(self.leer_seleccion)
        self.b_listar.clicked.connect(self.listar_servidor)
        return cont

    def _construir_ejecucion(self) -> QWidget:
        cont = QWidget()
        capa = QVBoxLayout(cont)
        fila = QHBoxLayout()
        for i, nombre in enumerate(PASOS, 1):
            e = QLabel("○ %d. %s" % (i, nombre))
            e.setWordWrap(True)
            self._pasos.append(e)
            fila.addWidget(e)
        capa.addLayout(fila)
        self.resumen = QLabel("")
        self.resumen.setWordWrap(True)
        self.resumen.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        capa.addWidget(self.resumen)
        self.consola = ConsolaAnsi()
        capa.addWidget(self.consola, 1)
        return cont

    def _construir_mantenimiento(self) -> QWidget:
        cont = QWidget()
        capa = QVBoxLayout(cont)
        fila = QHBoxLayout()
        self.b_log = QPushButton("Registro del instalador")
        self.b_cron_ver = QPushButton("Ver crontab")
        self.b_cron_quitar = QPushButton("Quitar entradas de cron…")
        self.b_copias = QPushButton("Copias de seguridad")
        for b in (self.b_log, self.b_cron_ver, self.b_cron_quitar, self.b_copias):
            fila.addWidget(b)
        fila.addStretch(1)
        capa.addLayout(fila)
        self.salida_mant = ConsolaAnsi()
        capa.addWidget(self.salida_mant, 1)
        self.b_log.clicked.connect(self.ver_registro)
        self.b_cron_ver.clicked.connect(self.ver_cron)
        self.b_cron_quitar.clicked.connect(self.quitar_cron)
        self.b_copias.clicked.connect(self.ver_copias)
        return cont

    # ====================================================================== formulario <-> opciones
    def opciones(self) -> OpcionesInstalador:
        seleccion = next((k for k, r in self.radios.items() if r.isChecked()), SELECCION_GUARDADA)
        repos, excluir = self._marcados()
        return OpcionesInstalador(
            variante=self.variante.currentData(), usuario_gh=self.usuario_gh.text().strip(),
            origen=self.origen.text().strip(), destino=self.destino.text().strip(), docroot=self.docroot.text().strip(),
            forzar=self.forzar.isChecked(), seleccion=seleccion, repos=repos if seleccion == SELECCION_LISTA else [],
            excluir=excluir if seleccion == SELECCION_EXCLUIR else [], modo=self.modo.currentData(),
            sin_indice=self.sin_indice.isChecked(), colector=self.colector.isChecked(), cron=self.cron.text().strip(),
            url=self.url.text().strip(), entrada_raiz=self.entrada_raiz.isChecked(), json_dir=self.json_dir.text().strip(),
            dir_script=self.dir_script.text().strip())

    def poner_opciones(self, o: OpcionesInstalador) -> None:
        self._opciones_cargando = True
        try:
            self.variante.setCurrentIndex(max(self.variante.findData(o.variante), 0))
            self.usuario_gh.setText(o.usuario_gh)
            self.origen.setText(o.origen)
            self.destino.setText(o.destino)
            self.docroot.setText(o.docroot)
            self.dir_script.setText(o.dir_script)
            self.forzar.setChecked(o.forzar)
            self.modo.setCurrentIndex(max(self.modo.findData(o.modo), 0))
            self.sin_indice.setChecked(o.sin_indice)
            self.colector.setChecked(o.colector)
            self.estacion.setEnabled(o.colector)
            self.clave_api.setEnabled(o.colector)
            self.cron.setText(o.cron)
            self.url.setText(o.url)
            self.entrada_raiz.setChecked(o.entrada_raiz)
            self.json_dir.setText(o.json_dir)
            self.radios[o.seleccion].setChecked(True)
            self._repos_sel_pendiente = set(o.repos if o.seleccion == SELECCION_LISTA else o.excluir)
        finally:
            self._opciones_cargando = False
        self._cambiado()

    def _preset_cron(self) -> None:
        valor = self.cron_preset.currentData()
        if valor is not None and self.cron_preset.currentIndex() > 0:
            self.cron.setText(valor)

    def _cambiado(self, *_args) -> None:
        if self._opciones_cargando or not self._construido:
            return
        o = self.opciones()
        isa = o.variante == VARIANTE_ISA
        self.g_isa.setEnabled(isa)
        self.docroot.setPlaceholderText(OpcionesInstalador(variante=o.variante).docroot_efectivo())
        self.destino.setPlaceholderText(OpcionesInstalador(variante=o.variante, docroot=o.docroot).destino_efectivo())
        self.arbol.setEnabled(o.seleccion in (SELECCION_LISTA, SELECCION_EXCLUIR))
        errores = o.validar()
        self.vista_previa.setText(o.comando_equivalente())
        if errores:
            self.barra.poner(errores[0], "aviso")
        elif not self.ocupada:
            self.barra.poner("")

    # ====================================================================== árbol de repos
    def _marcados(self) -> tuple:
        """(lista «repo» / «repo/carpeta», lista de repos para excluir) según lo marcado en el árbol."""
        repos, excluir = [], []
        for i in range(self.arbol.topLevelItemCount()):
            it = self.arbol.topLevelItem(i)
            nombre = it.text(0)
            if it.checkState(0) == Qt.CheckState.Checked:
                repos.append(nombre)
                excluir.append(nombre)
                continue
            for j in range(it.childCount()):
                h = it.child(j)
                if h.data(0, Qt.ItemDataRole.UserRole) != PLACEHOLDER and h.checkState(0) == Qt.CheckState.Checked:
                    repos.append("%s/%s" % (nombre, h.text(0)))
        if not self.arbol.topLevelItemCount():           # árbol sin cargar: conservar la selección guardada del perfil
            repos = sorted(self._repos_sel_pendiente) if self.radios[SELECCION_LISTA].isChecked() else []
            excluir = sorted(self._repos_sel_pendiente) if self.radios[SELECCION_EXCLUIR].isChecked() else []
        return repos, excluir

    def _marcar_todos(self, marcar: bool) -> None:
        self.arbol.blockSignals(True)
        for i in range(self.arbol.topLevelItemCount()):
            self.arbol.topLevelItem(i).setCheckState(0, Qt.CheckState.Checked if marcar else Qt.CheckState.Unchecked)
        self.arbol.blockSignals(False)
        self._cambiado()

    def cargar_repos(self) -> None:
        usuario, token = self.usuario_gh.text().strip(), self.ctx.ajustes.token_github

        def trabajo(t):
            try:
                return github.listar_repos(usuario, token)
            except github.ErrorGitHub as exc:
                return exc

        def listo(repos):
            if isinstance(repos, Exception):
                self.barra.poner(str(repos), "error")
                return
            self.arbol.blockSignals(True)
            self.arbol.clear()
            for r in repos:
                it = QTreeWidgetItem([r.nombre, r.lenguaje, str(r.tamano_kb)])
                it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                it.setCheckState(0, Qt.CheckState.Unchecked)
                it.setToolTip(0, r.descripcion)
                ph = QTreeWidgetItem(["cargando carpetas…"])
                ph.setData(0, Qt.ItemDataRole.UserRole, PLACEHOLDER)
                it.addChild(ph)
                self.arbol.addTopLevelItem(it)
                if r.nombre in self._repos_sel_pendiente:
                    it.setCheckState(0, Qt.CheckState.Checked)
            self.arbol.blockSignals(False)
            ajustar_arbol(self.arbol)
            self.barra.poner("%d repos (sin archivados)." % len(repos), "ok")
            self._cambiado()

        self.correr("Consultando GitHub…", trabajo, listo, deshabilitar=[self.b_cargar])

    def _expandido(self, item: QTreeWidgetItem) -> None:
        """Al desplegar un repo se piden sus carpetas (una sola vez)."""
        if item.childCount() != 1 or item.child(0).data(0, Qt.ItemDataRole.UserRole) != PLACEHOLDER:
            return
        repo, usuario, token = item.text(0), self.usuario_gh.text().strip(), self.ctx.ajustes.token_github

        def rellenar(carpetas):
            item.takeChildren()
            self.arbol.blockSignals(True)
            for c in carpetas:
                h = QTreeWidgetItem([c])
                h.setFlags(h.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                marcada = "%s/%s" % (repo, c) in self._repos_sel_pendiente
                h.setCheckState(0, Qt.CheckState.Checked if marcada else Qt.CheckState.Unchecked)
                item.addChild(h)
            if not carpetas:
                vacio = QTreeWidgetItem(["(sin carpetas)"])
                vacio.setFlags(Qt.ItemFlag.NoItemFlags)
                item.addChild(vacio)
            self.arbol.blockSignals(False)
            ajustar_arbol(self.arbol)

        def fallo(texto):
            item.takeChildren()
            e = QTreeWidgetItem(["no se pudieron leer: " + texto.strip().splitlines()[-1]])
            e.setFlags(Qt.ItemFlag.NoItemFlags)
            item.addChild(e)

        self.ctx.lanzar(lambda t: github.listar_carpetas(usuario, repo, token), "carpetas de " + repo,
                        al_terminar=rellenar, al_error=fallo)

    # ====================================================================== servidor activo
    def perfil_cambiado(self) -> None:
        p = self.perfil
        hay = p is not None
        for b in (self.b_instalar, self.b_guardar, self.b_leer_sel, self.b_listar, self.b_log, self.b_cron_ver,
                  self.b_cron_quitar, self.b_copias):
            b.setEnabled(hay)
        self.arbol.clear()
        self.sel_servidor.clear()
        self.salida_mant.clear()
        self.consola.clear()
        self.resumen.setText("")
        self._reiniciar_pasos()
        if p:
            o = OpcionesInstalador.desde_dict(p.instalador)
            if not p.instalador:                       # primer uso: valores sensatos según la variante del perfil
                o.variante = p.variante
                o.usuario_gh = self.ctx.ajustes.usuario_github
                o.url = p.url_base if o.variante == VARIANTE_ISA else ""
            self.poner_opciones(o)
        else:
            self.poner_opciones(OpcionesInstalador())

    def guardar_predeterminado(self) -> None:
        if not self.hay_perfil():
            return
        self.perfil.instalador = self.opciones().a_dict()
        self.perfil.variante = self.variante.currentData()
        self.ctx.almacen.actualizar(self.perfil)
        self.barra.poner("Opciones guardadas en el servidor «%s» (la clave API no se guarda)." % self.perfil.etiqueta(), "ok")

    # ====================================================================== ejecución
    def _reiniciar_pasos(self) -> None:
        for i, e in enumerate(self._pasos, 1):
            e.setText("○ %d. %s" % (i, PASOS[i - 1]))
            estilo.poner_rol(e, "")

    def _marcar_paso(self, ev: instalador.EventoLog) -> None:
        if ev.tipo == "fin":
            for i, e in enumerate(self._pasos, 1):
                if e.text().startswith("▶"):
                    e.setText("✔ %d. %s" % (i, PASOS[i - 1]))
                    estilo.poner_rol(e, "ok")
            return
        for i, e in enumerate(self._pasos, 1):
            if i < ev.paso and not e.text().startswith("✔"):
                e.setText("✔ %d. %s" % (i, PASOS[i - 1]))
                estilo.poner_rol(e, "ok")
            elif i == ev.paso:
                e.setText("▶ %d. %s" % (i, PASOS[i - 1]))
                estilo.poner_rol(e, "activo")

    def instalar(self, saltar_confirmacion: bool = False) -> None:
        if not self.hay_perfil():
            return
        o = self.opciones()
        errores = o.validar()
        if errores:
            self.error("Revisa la configuración:\n\n• " + "\n• ".join(errores))
            return
        recursos = self.ctx.recursos()
        nombre = Recursos.nombre_instalador(o.variante)
        if recursos.ruta(nombre) is None:
            self.error("No se encuentra «%s». Usa Preferencias → Actualizar scripts desde GitHub." % nombre)
            return
        perfil, con = self.perfil, self.ctx.conexion(self.perfil)
        if not saltar_confirmacion and not self.confirmar(
                "Instalar / actualizar",
                "Se ejecutará en %s:\n\n%s\n\nDestino: %s\n%s%s" % (
                    perfil.etiqueta(), o.comando_equivalente(), o.destino_efectivo(),
                    "Se instalará el servicio del colector.\n" if o.colector else "",
                    "Se programará cron: %s\n" % o.cron if o.cron else "")):
            return
        credenciales = {}
        if o.colector:
            if self.estacion.text().strip():
                credenciales["TELEMET_STATION_ID"] = self.estacion.text().strip()
            if self.clave_api.text():
                credenciales["TELEMET_API_KEY"] = self.clave_api.text()
        self.guardar_predeterminado_silencioso(o)
        self.consola.clear()
        self.resumen.setText("")
        self._reiniciar_pasos()
        self.pestanas.setCurrentIndex(2)

        def trabajo(t):
            return instalador.ejecutar_instalador(
                con, recursos, o, credenciales, al_linea=lambda texto, e: t.linea(texto, e),
                al_paso=lambda ev: hilos.en_gui(lambda: self._marcar_paso(ev)), cancelador=t.cancelador)

        def listo(res: instalador.ResultadoInstalacion):
            self.ctx.sesion_cambiada.emit(perfil.id)
            if res.necesita_forzar and not o.forzar:
                if self.confirmar("Destino con contenido ajeno",
                                  "El destino ya tiene contenido que no creó este instalador y el script no puede "
                                  "preguntar sin terminal.\n\n¿Repetir con --forzar? Se guardará antes una copia de lo "
                                  "que se sustituya o borre.", forzar=True):
                    self.forzar.setChecked(True)
                    self.instalar(saltar_confirmacion=True)
                    return
            self._mostrar_resultado(res)

        self.correr("Instalando en %s…" % perfil.etiqueta(), trabajo, listo,
                    deshabilitar=[self.b_instalar, self.b_listar, self.b_leer_sel],
                    al_linea=lambda texto, e: self.consola.anadir(texto, e))

    def guardar_predeterminado_silencioso(self, o: OpcionesInstalador) -> None:
        d = o.a_dict()
        d["forzar"] = False                      # --forzar nunca se recuerda: debe decidirse en cada ocasión
        self.perfil.instalador = d
        self.ctx.almacen.actualizar(self.perfil)

    def _mostrar_resultado(self, res: instalador.ResultadoInstalacion) -> None:
        r = res.resumen
        partes = []
        if "nuevos" in r:
            partes.append("Repos: %d nuevos, %d actualizados (%d con cambios), %d errores." % (
                r["nuevos"], r["actualizados"], r["con_cambios"], r.get("errores_repos", 0)))
        if "desplegados_nuevos" in r:
            partes.append("Despliegue: %d nuevos, %d modificados, %d borrados, %s." % (
                r["desplegados_nuevos"], r["desplegados_modificados"], r["desplegados_borrados"], r["transferido"]))
        if "url" in r:
            partes.append("Entrada: %s · %d error(es) · %d s" % (r["url"], r["errores"], r["segundos"]))
        if res.mensaje:
            partes.append(res.mensaje)
        self.resumen.setText("\n".join(partes))
        if res.ok and not res.errores:
            self.barra.poner("Instalación terminada sin errores.", "ok")
            estilo.poner_rol(self.resumen, "ok")
        elif res.ok:
            self.barra.poner("Terminó con %d error(es) en el registro." % len(res.errores), "aviso")
            estilo.poner_rol(self.resumen, "aviso")
        else:
            self.barra.poner(res.mensaje.splitlines()[0] if res.mensaje else "El instalador falló (código %d)." % res.codigo, "error")
            estilo.poner_rol(self.resumen, "error")

    # ====================================================================== repositorios en el servidor
    def leer_seleccion(self) -> None:
        if not self.hay_perfil():
            return
        o, con = self.opciones(), self.ctx.conexion(self.perfil)

        def trabajo(t):
            return instalador.leer_seleccion_guardada(con, o)

        def listo(lineas):
            self.sel_servidor.setPlainText("\n".join(lineas) or "(vacía: el script preguntará o usará --todos)")
            self._repos_sel_pendiente = set(lineas)
            self.barra.poner("%d entradas en la selección guardada." % len(lineas), "ok")

        self.correr("Leyendo .seleccion…", trabajo, listo, deshabilitar=[self.b_leer_sel])

    def listar_servidor(self) -> None:
        if not self.hay_perfil():
            return
        o, con, recursos = self.opciones(), self.ctx.conexion(self.perfil), self.ctx.recursos()
        self.sel_servidor.clear()

        def trabajo(t):
            return instalador.listar_en_servidor(con, recursos, o, lambda texto, e: t.linea(texto, e), t.cancelador)

        def listo(res):
            self.barra.poner("Listado terminado." if res.ok else res.mensaje, "ok" if res.ok else "error")

        self.correr("Ejecutando --listar…", trabajo, listo, deshabilitar=[self.b_listar],
                    al_linea=lambda texto, e: self.sel_servidor.appendPlainText(texto))

    # ====================================================================== mantenimiento
    def _mostrar(self, texto: str) -> None:
        self.salida_mant.clear()
        self.salida_mant.anadir(texto or "(vacío)")

    def _leer(self, titulo: str, funcion) -> None:
        if not self.hay_perfil():
            return
        o, con = self.opciones(), self.ctx.conexion(self.perfil)

        def trabajo(t):
            try:
                return funcion(con, o)
            except RuntimeError as exc:
                return "ERROR: %s" % exc

        self.correr(titulo, trabajo, lambda txt: (self._mostrar(txt), self.barra.poner("Listo.", "ok")),
                    deshabilitar=[self.b_log, self.b_cron_ver, self.b_cron_quitar, self.b_copias])

    def ver_registro(self) -> None:
        self._leer("Leyendo registro del instalador…", lambda con, o: instalador.leer_registro(con, o, 400))

    def ver_cron(self) -> None:
        self._leer("Leyendo crontab…", lambda con, o: instalador.leer_crontab(con) or "(crontab vacío)")

    def ver_copias(self) -> None:
        self._leer("Buscando copias de seguridad…",
                   lambda con, o: "\n".join(instalador.listar_copias(con)) or "(no hay copias en /var/backups)")

    def quitar_cron(self) -> None:
        if not self.hay_perfil():
            return
        con = self.ctx.conexion(self.perfil)
        if not self.confirmar("Quitar del cron", "Se quitarán del crontab de %s todas las líneas que contengan "
                                                 "«instalar-todo». ¿Continuar?" % self.perfil.etiqueta(), forzar=True):
            return

        def trabajo(t):
            actual = instalador.leer_crontab(con)
            nuevo, quitadas = instalador.quitar_entradas_cron(actual)
            if not quitadas:
                return "No había entradas de instalar-todo en el crontab."
            r = instalador.escribir_crontab(con, nuevo)
            if not r.ok:
                return "ERROR al escribir el crontab: " + r.error
            return "Quitadas %d línea(s):\n%s" % (len(quitadas), "\n".join(quitadas))

        self.correr("Quitando entradas de cron…", trabajo, lambda txt: (self._mostrar(txt), self.barra.poner("Listo.", "ok")),
                    deshabilitar=[self.b_cron_quitar])
