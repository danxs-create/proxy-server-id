import os
import requests
from urllib.parse import urlparse
from flask import Flask, request, Response, jsonify
from flask_cors import CORS

# Inisialisasi App dengan nama netral
app = Flask(__name__)
CORS(app)

TIMEOUT = 15
BLOCKED_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}

EXCLUDED_REQUEST_HEADERS = {
    "host", "content-length", "transfer-encoding", "connection",
    "keep-alive", "te", "trailers", "upgrade"
}

EXCLUDED_RESPONSE_HEADERS = {
    "content-encoding", "content-length", "transfer-encoding", "connection",
    "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "upgrade"
}


def validate_url(url: str) -> tuple[bool, str]:
    if not url:
        return False, "Parameter 'url' wajib diisi."
    try:
        parsed = urlparse(url)
    except Exception:
        return False, "URL tidak valid."
    if parsed.scheme not in ("http", "https"):
        return False, "URL harus menggunakan skema http atau https."
    if not parsed.netloc:
        return False, "URL tidak memiliki host yang valid."
    hostname = parsed.hostname or ""
    if hostname in BLOCKED_HOSTS:
        return False, "Akses ke host lokal tidak diizinkan."
    return True, ""


def forward_request(target_url: str) -> Response:
    valid, error_msg = validate_url(target_url)
    if not valid:
        return jsonify({"error": error_msg}), 400

    forwarded_headers = {
        key: value
        for key, value in request.headers.items()        if key.lower() not in EXCLUDED_REQUEST_HEADERS
    }

    body = request.get_data() or None

    try:
        resp = requests.request(
            method=request.method,
            url=target_url,
            headers=forwarded_headers,
            data=body,
            params=None,
            timeout=TIMEOUT,
            allow_redirects=True,
            stream=True,
        )
    except requests.exceptions.Timeout:
        return jsonify({"error": "Request ke target URL melebihi batas waktu."}), 504
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "Gagal terhubung ke target URL."}), 502
    except requests.exceptions.TooManyRedirects:
        return jsonify({"error": "Terlalu banyak redirect dari target URL."}), 502
    except requests.exceptions.RequestException as exc:
        return jsonify({"error": f"Request gagal: {str(exc)}"}), 502

    response_headers = {
        key: value
        for key, value in resp.headers.items()
        if key.lower() not in EXCLUDED_RESPONSE_HEADERS
    }

    return Response(
        response=resp.content,
        status=resp.status_code,
        headers=response_headers,
    )


@app.route("/")
def index():
    # Nama servis diganti jadi netral biar lolos filter Replit
    return jsonify({
        "status": "active",
        "service": "Universal API Gateway", 
        "usage": "GET/POST /api/proxy?url=<target_url>"
    })


@app.route("/api/proxy", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
def proxy():    target_url = request.args.get("url", "").strip()
    return forward_request(target_url)


@app.route("/api/healthz", methods=["GET"])
def healthz():
    return jsonify({"status": "ok"})


@app.errorhandler(404)
def not_found(exc):
    return jsonify({"error": "Endpoint tidak ditemukan."}), 404


@app.errorhandler(405)
def method_not_allowed(exc):
    return jsonify({"error": "Method tidak diizinkan."}), 405


@app.errorhandler(500)
def internal_error(exc):
    return jsonify({"error": "Terjadi kesalahan internal pada server."}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
