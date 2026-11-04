# Apache en Debian 13: publicar en `/var/www/html` o en `/var/www/htdocs`

Guía para el servidor local `192.168.0.129` y el script `instalar_todo.sh`.

Autor: Rafael Puerto · Departamento de Ingeniería de Sistemas y Automática · UMH · r.puerto@umh.es
_Generado con IA · Revisado por el autor_ · Última modificación: 04/11/2026 01:58

---

## 1. Qué pasa

Apache solo publica lo que está dentro de su **`DocumentRoot`**. En un Debian 13 recién instalado es **`/var/www/html`**. La carpeta `/var/www/htdocs` es la convención de otros servidores (por ejemplo, el de `isa.umh.es`), pero **este Debian no la sirve** salvo que se configure.

| Valor de `DOCROOT` en el script | Resultado |
|---|---|
| `/var/www/html` | Funciona: `http://192.168.0.129/rafa/` responde. |
| `/var/www/htdocs` | Los ficheros se copian, pero Apache no los sirve: **404 Not Found**. |

No es un fallo del script: el script copia a la carpeta que se le indica, y esa carpeta tiene que ser una que Apache publique.

## 2. Comprobar qué carpeta sirve tu Apache

```bash
grep -rn "DocumentRoot" /etc/apache2/sites-enabled/ /etc/apache2/apache2.conf
sudo apache2ctl -S
ls /var/www/
curl -sI http://localhost/rafa/ | head -1
```

- El `DocumentRoot` que aparezca en `sites-enabled` es la carpeta publicada.
- Un **404** en `/rafa/` indica que la ruta no existe dentro de esa carpeta.
- Un **403** indicaría un problema de permisos de Apache, no de ruta.

## 3. Opciones

### Opción recomendada: usar `/var/www/html`

No hay que configurar nada en Apache. Es la opción por defecto del script:

```bash
./instalar_todo.sh -d /var/www/html/rafa
```

Si el destino anterior (`/var/www/htdocs/rafa`) ya no se usa, puedes revisarlo y borrarlo cuando quieras. Apache no lo sirve.

### Opción A: cambiar el `DocumentRoot` a `/var/www/htdocs`

Úsala si necesitas que `/var/www/htdocs` sea la raíz de este servidor.

```bash
sudo sed -i 's|DocumentRoot /var/www/html|DocumentRoot /var/www/htdocs|' /etc/apache2/sites-available/000-default.conf
sudo apache2ctl configtest && sudo systemctl reload apache2
./instalar_todo.sh --docroot /var/www/htdocs
```

- `/etc/apache2/apache2.conf` ya concede acceso a todo `/var/www/`, así que no hace falta añadir un bloque `<Directory>`.
- La raíz del servidor pasa a ser `/var/www/htdocs`. Deja de servirse `/var/www/html`.
- Si ya tenías contenido en `/var/www/htdocs/rafa`, el script lo listará y pedirá confirmación (ver la guía de `instalar_todo.sh`).

### Opción B: mantener `/var/www/html` como raíz y publicar solo `/rafa` desde htdocs

```bash
sudo tee /etc/apache2/conf-available/rafa-alias.conf >/dev/null <<'EOF'
Alias /rafa /var/www/htdocs/rafa
<Directory /var/www/htdocs/rafa>
    Require all granted
</Directory>
EOF
sudo a2enconf rafa-alias
sudo apache2ctl configtest && sudo systemctl reload apache2
./instalar_todo.sh --docroot /var/www/htdocs
```

- `http://192.168.0.129/rafa/` se sirve desde `/var/www/htdocs/rafa` sin cambiar la raíz del servidor.
- Limitación: el script toma `--docroot` como la raíz real de Apache y, en el paso 5, busca ahí un `index.html` o `.htaccess` antiguos con referencias a `moda`. Si tu raíz real sigue siendo `/var/www/html`, esa limpieza **no se aplicará** a sus ficheros; revísalos a mano.

## 4. Comprobación final

```bash
curl -sI http://192.168.0.129/      | head -3   # 302 → /rafa/
curl -sI http://192.168.0.129/rafa/ | head -1   # 200
```

Si sigue sin funcionar, reúne esta información:

```bash
sudo apache2ctl -S
sudo tail -n 30 /var/log/apache2/error.log
ls -la /var/www/ /var/www/htdocs/rafa | head -20
```

## 5. Resumen

| Quiero… | Haz esto |
|---|---|
| Lo más sencillo | Usar `/var/www/html` (por defecto). |
| Que `/var/www/htdocs` sea la raíz del servidor | Opción A: cambiar `DocumentRoot` y usar `--docroot /var/www/htdocs`. |
| Mantener la raíz actual y servir solo `/rafa` desde htdocs | Opción B: `Alias` y `--docroot /var/www/htdocs`. |
