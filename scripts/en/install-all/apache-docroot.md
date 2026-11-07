# Apache on Debian 13: publishing from `/var/www/html` or `/var/www/htdocs`

Guide for the local server `192.168.0.129` and the `install-all.sh` script.

Author: Rafael Puerto · Department of Systems Engineering and Automation · UMH · r.puerto@umh.es
_Generated with AI · Reviewed by the author_ · Last modified: 2026-11-04 02:38

---

## 1. What happens

Apache only publishes what is inside its **`DocumentRoot`**. On a freshly installed Debian 13 it is **`/var/www/html`**. The folder `/var/www/htdocs` is the convention of other servers (for example, the one at `isa.umh.es`), but **this Debian does not serve it** unless it is configured.

| `DOCROOT` value in the script | Result |
|---|---|
| `/var/www/html` | Works: `http://192.168.0.129/rafa/` answers. |
| `/var/www/htdocs` | The files are copied, but Apache does not serve them: **404 Not Found**. |

It is not a script failure: the script copies to the folder it is given, and that folder has to be one that Apache publishes.

## 2. Check which folder your Apache serves

```bash
grep -rn "DocumentRoot" /etc/apache2/sites-enabled/ /etc/apache2/apache2.conf
sudo apache2ctl -S
ls /var/www/
curl -sI http://localhost/rafa/ | head -1
```

- The `DocumentRoot` that shows up in `sites-enabled` is the published folder.
- A **404** on `/rafa/` means the path does not exist inside that folder.
- A **403** would indicate an Apache permissions problem, not a path problem.

## 3. Options

### Recommended option: use `/var/www/html`

Nothing needs to be configured in Apache. It is the script's default:

```bash
./install-all.sh -d /var/www/html/rafa
```

If the previous destination (`/var/www/htdocs/rafa`) is no longer used, you can review it and delete it whenever you want. Apache does not serve it.

### Option A: change the `DocumentRoot` to `/var/www/htdocs`

Use it if you need `/var/www/htdocs` to be the root of this server.

```bash
sudo sed -i 's|DocumentRoot /var/www/html|DocumentRoot /var/www/htdocs|' /etc/apache2/sites-available/000-default.conf
sudo apache2ctl configtest && sudo systemctl reload apache2
./install-all.sh --docroot /var/www/htdocs
```

- `/etc/apache2/apache2.conf` already grants access to all of `/var/www/`, so no `<Directory>` block is needed.
- The server root becomes `/var/www/htdocs`. `/var/www/html` is no longer served.
- If you already had content in `/var/www/htdocs/rafa`, the script will list it and ask for confirmation (see the `install-all.sh` guide).

### Option B: keep `/var/www/html` as the root and publish only `/rafa` from htdocs

```bash
sudo tee /etc/apache2/conf-available/rafa-alias.conf >/dev/null <<'EOF'
Alias /rafa /var/www/htdocs/rafa
<Directory /var/www/htdocs/rafa>
    Require all granted
</Directory>
EOF
sudo a2enconf rafa-alias
sudo apache2ctl configtest && sudo systemctl reload apache2
./install-all.sh --docroot /var/www/htdocs
```

- `http://192.168.0.129/rafa/` is served from `/var/www/htdocs/rafa` without changing the server root.
- Limitation: the script takes `--docroot` as the real Apache root and, in step 5, looks there for an old `index.html` or `.htaccess` with references to `moda`. If your real root is still `/var/www/html`, that cleanup **will not be applied** to its files; review them by hand.

## 4. Final check

```bash
curl -sI http://192.168.0.129/      | head -3   # 302 → /rafa/
curl -sI http://192.168.0.129/rafa/ | head -1   # 200
```

If it still does not work, gather this information:

```bash
sudo apache2ctl -S
sudo tail -n 30 /var/log/apache2/error.log
ls -la /var/www/ /var/www/htdocs/rafa | head -20
```

## 5. Summary

| I want… | Do this |
|---|---|
| The simplest thing | Use `/var/www/html` (default). |
| `/var/www/htdocs` to be the server root | Option A: change `DocumentRoot` and use `--docroot /var/www/htdocs`. |
| Keep the current root and serve only `/rafa` from htdocs | Option B: `Alias` and `--docroot /var/www/htdocs`. |
