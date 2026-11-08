# Cloning and updating the public repositories of RafaUMH2110

Guide for a local **Debian 13** server (IP `192.168.0.129`).

Author: Rafa Puerto · Department of Systems Engineering and Automation · UMH · r.puerto@umh.es
_Generated with AI · Reviewed by the author_

---

## 1. Requirements

```bash
sudo apt update && sudo apt install -y git curl jq
```

| Package | Use |
|---------|-----|
| `git`   | Clone and update repositories |
| `curl`  | Query the GitHub API |
| `jq`    | Process the JSON response of the API |

The server needs Internet access (HTTPS, port 443) to `github.com` and `api.github.com`.

## 2. Clone all public repos (first time)

```bash
mkdir -p ~/RafaUMH2110 && cd ~/RafaUMH2110

page=1
while :; do
  repos=$(curl -s "https://api.github.com/users/RafaUMH2110/repos?type=public&per_page=100&page=$page" \
    | jq -r '.[].name')
  [ -z "$repos" ] && break
  for r in $repos; do
    if [ -d "$r/.git" ]; then
      echo ">> Updating $r"; git -C "$r" pull --ff-only
    else
      echo ">> Cloning $r"
      git clone "https://github.com/RafaUMH2110/$r.git"
    fi
  done
  page=$((page+1))
done
```

Result: one directory per repository inside `~/RafaUMH2110/`.

## 3. Update script (`update-repos.sh`)

It runs `git pull --ff-only` on the repos already cloned, clones the new public ones, copies the `.html` files to Apache and writes a log in `update.log`. The full script is in this folder: [`update-repos.sh`](update-repos.sh).

```bash
chmod +x update-repos.sh

./update-repos.sh                                   # defaults: ~/RafaUMH2110 and /var/www/html/rafa
./update-repos.sh /srv/repos /var/www/html/rafa     # custom directories
```

The deployment to Apache can also be done on its own with [`deploy-apache.sh`](deploy-apache.sh):

```bash
./deploy-apache.sh -o ~/RafaUMH2110 -d /var/www/html/rafa [--html-only] [--no-index] [-n]
```

| Option | Meaning |
|---|---|
| `-o SOURCE` | Directory with the cloned repos |
| `-d DEST` | Apache directory |
| `--html-only` | Copy only `*.html` / `*.htm` |
| `--no-index` | Do not generate the root `index.html` |
| `-n` | Dry run (changes nothing) |

> Both scripts are superseded by `install-all.sh` (see `../install-all/`), which adds repo selection, a visual portal and the collector.

## 4. Automate with cron

```bash
crontab -e
```

Add (daily run at 3:00):

```
0 3 * * * /home/user/update-repos.sh >/dev/null 2>&1
```

Replace `user` with the real user of the server. Check the result in `~/RafaUMH2110/update.log`.

## 5. Clone or update a single repository

```bash
# Clone
git clone https://github.com/RafaUMH2110/<repo>.git

# Update
git -C ~/RafaUMH2110/<repo> pull --ff-only
```

## 6. Private repositories (optional)

With a _Personal Access Token_ (`repo` scope) the private ones can be included:

```bash
export GITHUB_TOKEN="ghp_XXXXXXXXXXXX"
curl -s -H "Authorization: Bearer $GITHUB_TOKEN" \
  "https://api.github.com/user/repos?affiliation=owner&per_page=100&page=1" | jq -r '.[].name'
```

Recommendations:
- Do not leave the token written in the script or in the clone URL (it is stored in `.git/config`).
- A cleaner alternative: install `gh` (`sudo apt install gh`), run `gh auth login` and use `gh repo clone RafaUMH2110/<repo>`.

## 7. Exact backup-style copy (optional)

To keep all branches and references, clone with `--mirror` and update with `remote update`:

```bash
git clone --mirror https://github.com/RafaUMH2110/<repo>.git
git -C <repo>.git remote update --prune
```

A `--mirror` repository has no working tree (it is only the Git database).

## 8. Troubleshooting

| Symptom | Likely cause | Solution |
|---------|--------------|----------|
| `jq: parse error` or the script fails when querying the API | Unauthenticated API limit (60 requests/hour per IP) | Wait an hour or use a token |
| `fatal: Not possible to fast-forward` | Local changes or rewritten history on the remote | Check with `git status`; if there is nothing local to keep: `git fetch && git reset --hard origin/<branch>` |
| `Could not resolve host: github.com` | No DNS or no Internet access | Check `ping 8.8.8.8` and `/etc/resolv.conf`; review proxy or firewall |
| `Permission denied` when creating the directory | Permissions of the destination | Use a destination inside `$HOME` or fix the owner with `chown` |
| Cron does not run | Relative path or missing execute permission | Use an absolute path and `chmod +x` |

## 9. Quick checks

```bash
ls ~/RafaUMH2110                        # cloned repos
tail -n 20 ~/RafaUMH2110/update.log     # latest result
git -C ~/RafaUMH2110/<repo> log -1      # latest downloaded commit
```
