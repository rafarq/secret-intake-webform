---
name: secret-intake-webform
description: Use when a secret must reach the machine without passing through chat (API keys, tokens, passwords, credential files). Serves a one-time web form through an existing Cloudflare Tunnel and writes the value to a file with 600 permissions.
version: 1.0.0
author: Rafael Roa
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [security, secrets, cloudflare-tunnel, access, form]
---

# Secret intake over a one-time web form

## When to use

Your agent needs a secret that **must not travel through the chat** (API key, token, password,
`client_secret`, credential file): Telegram, WhatsApp, email and session transcripts all keep a copy,
and so do the gateway logs and the session backups.

Instead of asking for the value in the conversation, serve a **one-time web form**, give the human the
link (the link is fine over chat — the value is not), and have it write straight to a file on the
machine that needs it. The value is never displayed, never echoed back and never typed by the agent.

## The rule

**Never ask for or accept a secret in the chat.** Not as a message, not as an attachment, not "just
this once". If a form cannot be served, say so and stop; do not fall back to the chat.

## Requirements

- A machine where the agent runs (Linux or macOS) with Python 3 (standard library only).
- A **Cloudflare Tunnel** already configured for a domain you control, plus a hostname you can point
  at the local port the form listens on. Cloudflare Access in front of that hostname is what stops
  anyone else from reaching the form; without it, the random 16-hex path is the only protection.
- No new dependencies: the script uses `http.server` and `secrets`.

## Procedure

### 1. Start the form

```bash
python3 scripts/secret_form.py \
  --dest ~/.hermes/.env.new \
  --campo "API key of the billing service" \
  --puerto 8899 \
  --host token.example.com
```

| Flag | Meaning |
|---|---|
| `--dest` | File the value is written to (created with `600`, overwritten, never appended) |
| `--campo` | Field label the human sees |
| `--nota` | Optional extra HTML shown under the form (context, required scopes) |
| `--puerto` | Local port (default `8899`) |
| `--host` | Public hostname that routes to that port (default `token.example.com`; **set it per machine**) |
| `--workdir` | Where the form page is generated (default `/tmp/secret-form`) |

It prints the local URL and the public URL, then serves in the foreground. Read the 16-hex key from
the work directory (`ls /tmp/secret-form/`). The script serves **only** that one file by exact path
and answers `404` to everything else, including directory listings.

**If a person has to open the link, the form must outlive your own session.** Starting it as a child
process of the agent session (a background task, a `timeout`-limited command) kills it when that
session ends, and the human then finds a dead link — with the tunnel log showing
`connect: connection refused` on the port, which looks like a network fault but is not. Run it as a
user unit instead, and stop it when the value has arrived:

```bash
systemd-run --user --unit=formulario --collect \
  python3 scripts/secret_form.py --dest ~/.hermes/.env.new --campo "API key" --host token.example.com
systemctl --user stop formulario.service
```

### 2. Publish it through the tunnel

Add an ingress rule for the form hostname **before** the catch-all `http_status:404` line, create the
DNS route and restart `cloudflared`:

```yaml
# ~/.cloudflared/config.yml
ingress:
  - hostname: token.example.com
    service: http://127.0.0.1:8899
  - service: http_status:404
```

```bash
cloudflared tunnel route dns <tunnel-name> token.example.com
systemctl --user restart cloudflared.service
curl -s -o /dev/null -w '%{http_code}\n' https://token.example.com/<16hex>.html   # 200, or 302 with Access
```

Put an **Access application** in front of that hostname with an `allow` policy listing the human's
email addresses (policies are per hostname, so each person's form hostname gets their own). With
nothing listening on the port, Cloudflare answers **502**: that is expected, not a misconfiguration.

If the secret you are collecting *is* the Cloudflare API token, Access cannot be used to protect the
form (it would be circular): use a temporary hostname with no Access policy and rely on the random
path plus the fact that you take it down within minutes.

### 3. Hand over the link

Short message: the URL, what to paste into it, what the value will be used for, and what happens next.
Then wait. Do not ask for the value again, and do not offer the chat as an alternative.

### 4. Verify and use

```bash
stat -c '%a %s %n' <dest>      # 600 and a plausible size
```

**Never print the value.** If you must show something, show its length or the first four characters.
Once used, delete the temporary file (`shred -u` where available) and keep the secret only where it
belongs (the service's own env file or secret store).

### 5. Take it down (as soon as the value is received)

```bash
pkill -f "secret_form.py --dest <dest>"   # match the specific command line, not "secret_form.py"
rm -rf <workdir>                          # the generated page
shred -u <dest> 2>/dev/null || rm -f <dest>
```

Verify the port no longer listens and that the hostname answers `502` (or `302` if Access is in front).
Then report what was deployed and confirm that no copy of the value remains.

## Pitfalls

- **The served directory must contain nothing else.** The script serves one file by exact path for
  exactly this reason: a directory served with `python3 -m http.server` publishes every file next to
  it, including other credentials.
- **The form hostname must have a single label** (`token.example.com`, not `form.token.example.com`):
  Cloudflare's free Universal SSL certificate does not cover third-level names, and TLS fails with no
  useful error (`curl` exit 35).
- **`--host` must match the machine.** The script's default is one specific hostname; on another
  machine it prints a URL that routes nowhere. Pass `--host` explicitly everywhere, or edit the
  default in your own copy.
- **The destination file is overwritten, not appended.** To add a line to an existing `.env`, read it,
  edit it, write the result, then delete the temporary file holding the secret.
- **`pkill -f secret_form.py` can kill the shell that launched it** when the pattern matches that
  shell's own command line. Match the full command line instead, or kill by the PID holding the port.
- **Free the port before relaunching**: `ss -tlnp | grep 8899` and kill the old PID.
- **Launch it with a timeout** so it cannot stay up forever if nobody takes it down — but only when
  the human is on the other side *right now*. If the form has to wait, run it as a systemd user unit
  (above): a timeout, or any child process of the agent session, death-marches the form the moment
  that session ends.
- **When another user runs the form** (for example via `sudo -u`), the `--workdir` must belong to that
  user: if `root` creates it, the server dies with `PermissionError` when writing the page.
- **Never type a sudo password into a PTY**: the terminal echoes it into the session log. Authenticate
  with `SUDO_ASKPASS` pointing at a `700` file that `cat`s the value, and delete both files afterwards.
- Session duration on the Access policy is typically 24 h, so the human normally identifies only once.
- `.dev` and `.app` are HSTS-preloaded (HTTPS only); the tunnel provides the certificate, so nothing
  extra is needed on the server.

## Security model (be honest about it)

- The value is written to a file with `600` permissions on the machine that needs it, and nowhere else.
- Access (or, failing that, the unguessable path and a short lifetime) keeps other people out; the file
  contents are never rendered back to the browser after submission.
- The form still relies on the transport being HTTPS end-to-end, so **serve it only through the
  tunnel** — never over plain HTTP on a public interface.
- Anything the agent later does with the secret (writing it into a service config, a `.env`) is a
  separate action: announce it, and clean up the intermediate copies.
