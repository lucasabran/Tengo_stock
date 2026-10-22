"""
Canjea el código de autorización de Tiendanube por un access token
y lo guarda en .env (STORE_ID y ACCESS_TOKEN).

Uso: python obtener_token.py CODIGO
"""
import json
import os
import sys
import urllib.error
import urllib.request

AQUI = os.path.dirname(os.path.abspath(__file__))
RUTA_ENV = os.path.join(AQUI, ".env")


def leer_env():
    lineas = open(RUTA_ENV, encoding="utf-8").read().splitlines() if os.path.exists(RUTA_ENV) else []
    env = dict(l.split("=", 1) for l in lineas if "=" in l and not l.startswith("#"))
    return lineas, {k.strip(): v.strip() for k, v in env.items()}


def guardar(lineas, valores):
    pendientes = dict(valores)
    for i, l in enumerate(lineas):
        k = l.split("=", 1)[0].strip()
        if k in pendientes:
            lineas[i] = f"{k}={pendientes.pop(k)}"
    lineas += [f"{k}={v}" for k, v in pendientes.items()]
    with open(RUTA_ENV, "w", encoding="utf-8") as f:
        f.write("\n".join(lineas) + "\n")


def main():
    if len(sys.argv) != 2:
        sys.exit("Uso: python obtener_token.py CODIGO")
    lineas, env = leer_env()
    for clave in ("APP_ID", "CLIENT_SECRET"):
        if not env.get(clave):
            sys.exit(f"Falta {clave} en .env")

    cuerpo = json.dumps({
        "client_id": env["APP_ID"],
        "client_secret": env["CLIENT_SECRET"],
        "grant_type": "authorization_code",
        "code": sys.argv[1],
    }).encode()
    req = urllib.request.Request(
        f"https://www.tiendanube.com/apps/authorize/token",
        data=cuerpo, method="POST", headers={"Content-Type": "application/json",
                 "User-Agent": f"GarantiaExtendida ({env.get('CONTACT_EMAIL', '')})"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            resp = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        sys.exit(f"Error {e.code}: {e.read().decode()}")

    if "access_token" not in resp:
        sys.exit(f"Respuesta inesperada: {resp}")
    guardar(lineas, {"STORE_ID": resp["user_id"], "ACCESS_TOKEN": resp["access_token"]})
    print(f"Listo. Token guardado en .env (tienda {resp['user_id']}).")


if __name__ == "__main__":
    main()
