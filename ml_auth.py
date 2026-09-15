"""
Manejo de autenticacion OAuth de MercadoLibre.

Primer uso (una sola vez):
    python ml_auth.py login
Se abre el navegador para autorizar la app; MELi redirige a tu redirect_uri
con ?code=XXXX en la URL. Pegue ese code en la consola cuando se lo pida.
El token queda guardado en token.json (no lo subas a ningun repo publico).

Uso posterior (automatico, lo llaman los otros scripts):
    from ml_auth import get_valid_token
    token = get_valid_token()
"""
import json
import os
import sys
import time
import webbrowser

import requests
from dotenv import load_dotenv

load_dotenv()

TOKEN_FILE = "token.json"
AUTH_BASE = "https://auth.mercadolibre.com.ar/authorization"
TOKEN_URL = "https://api.mercadolibre.com/oauth/token"

CLIENT_ID = os.environ.get("ML_CLIENT_ID")
CLIENT_SECRET = os.environ.get("ML_CLIENT_SECRET")
REDIRECT_URI = os.environ.get("ML_REDIRECT_URI")


def _save(token_data):
    token_data["obtained_at"] = int(time.time())
    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        json.dump(token_data, f, indent=2)


def _load():
    if not os.path.exists(TOKEN_FILE):
        return None
    with open(TOKEN_FILE, encoding="utf-8") as f:
        return json.load(f)


def login():
    if not (CLIENT_ID and REDIRECT_URI):
        sys.exit("Faltan ML_CLIENT_ID / ML_REDIRECT_URI en el archivo .env")

    url = f"{AUTH_BASE}?response_type=code&client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}"
    print(f"Abriendo navegador para autorizar:\n{url}\n")
    webbrowser.open(url)
    code = input("Pegue aca el 'code' que aparece en la URL de redireccion: ").strip()

    resp = requests.post(TOKEN_URL, data={
        "grant_type": "authorization_code",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "code": code,
        "redirect_uri": REDIRECT_URI,
    })
    resp.raise_for_status()
    _save(resp.json())
    print("Listo. Token guardado en token.json")


def refresh():
    data = _load()
    if not data or "refresh_token" not in data:
        sys.exit("No hay refresh_token guardado. Corra: python ml_auth.py login")

    resp = requests.post(TOKEN_URL, data={
        "grant_type": "refresh_token",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": data["refresh_token"],
    })
    resp.raise_for_status()
    _save(resp.json())
    return _load()


def get_valid_token():
    data = _load()
    if not data:
        sys.exit("No hay token guardado. Corra primero: python ml_auth.py login")
    if time.time() - data["obtained_at"] > data.get("expires_in", 21600) - 300:
        data = refresh()
    return data["access_token"]


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "login":
        login()
    elif len(sys.argv) > 1 and sys.argv[1] == "refresh":
        refresh()
        print("Token renovado.")
    else:
        print(__doc__)
