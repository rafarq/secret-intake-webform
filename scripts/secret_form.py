#!/usr/bin/env python3
"""One-time web form that writes a secret to a file, so it never goes through the chat.

Serves ONLY /<16 hex>.html (the form) and accepts the POST at /save-<16 hex>,
writing the value to --dest with 600 permissions. Every other path: 404.

Usage:
  python3 secret_form.py --dest ~/.hermes/.env.new --campo "API key of the billing service" [--puerto 8899]
"""
import argparse
import os
import re
import secrets
import sys
import http.server
from urllib.parse import parse_qs

TEXTS = {
    "es": {
        "blurb": ("Pega el valor y pulsa Guardar. Viaja cifrado hasta el servidor y se guarda "
                  "con permisos <code>600</code>."),
        "button": "Guardar",
        "saved_title": "Guardado",
        "saved_body": "Ya puedes cerrar esta pestana y avisarme por el chat.",
        "not_found": "No encontrado.",
        "invalid": "No he recibido un valor valido.",
        "label": "Secreto",
        "received": "recibido",
        "reminder": "retirar: borrar la ruta DNS, el ingress y matar este proceso",
    },
    "en": {
        "blurb": ("Paste the value and press Save. It travels encrypted to the server and is stored "
                  "with <code>600</code> permissions."),
        "button": "Save",
        "saved_title": "Saved",
        "saved_body": "You can close this tab now and tell me in the chat.",
        "not_found": "Not found.",
        "invalid": "I did not receive a valid value.",
        "label": "Secret",
        "received": "received",
        "reminder": "cleanup: delete the DNS route, the ingress rule and kill this process",
    },
}

FORM = """<!DOCTYPE html>
<html lang="{lang}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{campo}</title>
<style>
 :root {{ color-scheme: light dark; }}
 body {{ font-family: -apple-system, system-ui, sans-serif; margin:0; padding:20px;
        max-width:640px; margin-inline:auto; line-height:1.45; }}
 h1 {{ font-size:1.25rem; margin:0 0 12px; }}
 label {{ display:block; font-weight:600; margin:16px 0 6px; }}
 textarea {{ width:100%; box-sizing:border-box; min-height:120px; padding:10px;
            font:0.95rem/1.35 ui-monospace, Menlo, monospace; border:1px solid #999;
            border-radius:8px; }}
 button {{ width:100%; margin-top:16px; padding:14px; font-size:1rem; font-weight:600;
          border:0; border-radius:10px; background:#b8860b; color:#fff; }}
 code {{ background:rgba(127,127,127,.15); padding:1px 5px; border-radius:4px; }}
</style></head><body>
<h1>{campo}</h1>
<p>{blurb}</p>
<form method="post" action="/save-{k}">
  <label for="token">{campo}</label>
  <textarea id="token" name="token" autocomplete="off" autocapitalize="off"
            autocorrect="off" spellcheck="false"></textarea>
  <button type="submit">{button}</button>
</form>
{nota}
</body></html>
"""

OK = ("<meta name='viewport' content='width=device-width,initial-scale=1'>"
      "<div style='font-family:-apple-system,system-ui,sans-serif;padding:24px'>"
      "<h2>{title}</h2><p>{body}</p></div>")


def make_handler(form_path: str, dest: str, campo: str, txt: dict):
    k = os.path.basename(form_path)[: -len(".html")]
    permitido = re.compile(r"^/[0-9a-f]{16}\.html$")

    class H(http.server.BaseHTTPRequestHandler):
        server_version = "secret-form"

        def _respond(self, code, body, ctype="text/html; charset=utf-8"):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Robots-Tag", "noindex, nofollow")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            ruta = self.path.split("?")[0]
            if (permitido.match(ruta) and os.path.isfile(form_path)
                    and ruta == "/" + os.path.basename(form_path)):
                self._respond(200, open(form_path, "rb").read())
            else:
                self._respond(404, txt["not_found"].encode(), "text/plain; charset=utf-8")

        def do_POST(self):
            if self.path != "/save-" + k:
                self._respond(404, txt["not_found"].encode(), "text/plain; charset=utf-8")
                return
            n = int(self.headers.get("Content-Length", "0"))
            q = parse_qs(self.rfile.read(n).decode("utf-8", "replace"))
            val = q.get("token", [""])[0].strip()
            if not val or any(c.isspace() for c in val):
                self._respond(400, txt["invalid"].encode())
                return
            with open(dest, "w") as f:
                f.write(val + "\n")
            os.chmod(dest, 0o600)
            print("%s: %s (%d chars)" % (txt["received"], campo, len(val)), flush=True)
            self._respond(200, OK.format(title=txt["saved_title"], body=txt["saved_body"]).encode())

        def log_message(self, *a):
            pass

    return H


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dest", required=True, help="file the secret is written to (600)")
    ap.add_argument("--campo", default=None, help="label shown on the form")
    ap.add_argument("--puerto", type=int, default=8899)
    ap.add_argument("--nota", default="", help="extra HTML shown under the form")
    ap.add_argument("--workdir", default="/tmp/secret-form")
    ap.add_argument("--host", default="token.example.com",
                    help="public tunnel hostname that routes to this port")
    ap.add_argument("--lang", default="en", choices=sorted(TEXTS),
                    help="language of the form's own texts")
    a = ap.parse_args()

    txt = TEXTS[a.lang]
    campo = a.campo or txt["label"]

    dest = os.path.expanduser(a.dest)
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    os.makedirs(a.workdir, exist_ok=True)
    k = secrets.token_hex(8)
    form_path = os.path.join(a.workdir, k + ".html")
    with open(form_path, "w") as f:
        f.write(FORM.format(campo=campo, k=k, nota=a.nota, lang=a.lang,
                            blurb=txt["blurb"], button=txt["button"]))
    os.chmod(a.workdir, 0o700)

    h = make_handler(form_path, dest, campo, txt)
    srv = http.server.ThreadingHTTPServer(("0.0.0.0", a.puerto), h)
    print("destino: %s" % dest)
    print("formulario local: http://127.0.0.1:%d/%s.html" % (a.puerto, k))
    print("por el tunel:      https://%s/%s.html" % (a.host, k))
    print(txt["reminder"], flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    sys.exit(main())
