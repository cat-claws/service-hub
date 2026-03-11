#!/usr/bin/env python3
from __future__ import annotations

import argparse, http.client, json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailer", "transfer-encoding", "upgrade", "host"}
CORS_H = "Content-Type, Authorization, ngrok-skip-browser-warning"
CORS_M = "GET,POST,PUT,PATCH,DELETE,OPTIONS"


def _norm(p: str) -> str:
    p = (p or "").strip()
    if not p:
        return "/"
    if p[0] != "/":
        p = "/" + p
    return p[:-1] if p != "/" and p.endswith("/") else p


def _load(cfg: Path):
    raw = json.loads(cfg.read_text(encoding="utf-8"))
    rs = raw.get("routes", [])
    if not isinstance(rs, list):
        raise RuntimeError("config key 'routes' must be a list")
    out = []
    for i, r in enumerate(rs):
        if not isinstance(r, dict):
            raise RuntimeError(f"routes[{i}] must be an object")
        p, t, s = r.get("prefix"), r.get("target"), r.get("strip_prefix", True)
        if not isinstance(p, str) or not isinstance(t, str) or not isinstance(s, bool):
            raise RuntimeError(f"routes[{i}] invalid: need prefix(str), target(str), strip_prefix(bool)")
        out.append({"prefix": _norm(p), "target": t, "strip_prefix": s})
    out.sort(key=lambda x: len(x["prefix"]), reverse=True)
    return out


def _pick(path: str, routes):
    for r in routes:
        p = r["prefix"]
        if p == "/" or path == p or path.startswith(p + "/"):
            return r
    return None


class Hub(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    config: Path
    bind_host: str
    bind_port: int

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", CORS_H)
        self.send_header("Access-Control-Allow-Methods", CORS_M)

    @staticmethod
    def _skip_resp_header(name: str) -> bool:
        n = name.lower()
        if n in HOP or n == "content-length":
            return True
        if n.startswith("access-control-allow-"):
            return True
        return False

    def _json(self, code: int, obj):
        b = json.dumps(obj, indent=2).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self._cors(); self.end_headers(); self.wfile.write(b)

    def do_OPTIONS(self):  # noqa: N802
        self.send_response(204)
        self._cors(); self.send_header("Content-Length", "0"); self.end_headers()

    def do_GET(self): self._dispatch()  # noqa: N802,E701
    def do_POST(self): self._dispatch()  # noqa: N802,E701
    def do_PUT(self): self._dispatch()  # noqa: N802,E701
    def do_PATCH(self): self._dispatch()  # noqa: N802,E701
    def do_DELETE(self): self._dispatch()  # noqa: N802,E701

    def _dispatch(self):
        u = urlparse(self.path)
        if u.path == "/healthz":
            return self._json(200, {"ok": True})
        try:
            routes = _load(self.config)
        except Exception as e:
            return self._json(500, {"error": f"config error: {e}"})
        if u.path == "/routes":
            return self._json(200, {"routes": routes})
        route = _pick(u.path, routes)
        if not route:
            return self._json(404, {"error": f"no route for path: {u.path}"})
        self._proxy(route, u)

    def _self_target(self, host: str, port: int) -> bool:
        if port != self.bind_port:
            return False
        h, u = self.bind_host.lower(), host.lower()
        local, wild = {"127.0.0.1", "localhost", "::1"}, {"0.0.0.0", "::"}
        return u == h or (u in local and (h in local or h in wild))

    def _proxy(self, route, req):
        t = urlparse(route["target"])
        if t.scheme not in {"http", "https"} or not t.hostname:
            return self._json(500, {"error": f"invalid route target: {route['target']}"})
        port = t.port or (443 if t.scheme == "https" else 80)
        if self._self_target(t.hostname, port):
            return self._json(508, {"error": f"route target points to hub itself ({t.hostname}:{port})"})

        path = req.path + (("?" + req.query) if req.query else "")
        p = route["prefix"]
        if route["strip_prefix"] and p != "/":
            path = "/" if path == p else (path[len(p):] if path.startswith(p + "/") else path)
        if t.path and t.path != "/":
            path = t.path.rstrip("/") + (path if path.startswith("/") else "/" + path)

        body = None
        if self.command in {"POST", "PUT", "PATCH"}:
            n = int(self.headers.get("Content-Length", "0") or "0")
            body = self.rfile.read(n) if n > 0 else b""

        hs = {k: v for k, v in self.headers.items() if k.lower() not in HOP}; hs["Host"] = t.netloc
        Conn = http.client.HTTPSConnection if t.scheme == "https" else http.client.HTTPConnection
        c = Conn(t.hostname, port, timeout=60)
        try:
            c.request(self.command, path, body=body, headers=hs)
            r = c.getresponse()
            rb = r.read()
        except Exception as e:
            c.close(); return self._json(502, {"error": f"upstream request failed: {e}"})

        self.send_response(r.status)
        for k, v in r.getheaders():
            if not self._skip_resp_header(k):
                self.send_header(k, v)
        self.send_header("Content-Length", str(len(rb)))
        self._cors(); self.end_headers(); self.wfile.write(rb); c.close()


def main():
    p = argparse.ArgumentParser(description="Lightweight local service hub")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=3031)
    p.add_argument("--config", default="hub_config.json")
    a = p.parse_args()
    cfg = Path(a.config).resolve()
    if not cfg.exists():
        print(f"config not found: {cfg}")
        return 2
    H = type("ConfiguredHub", (Hub,), {})
    H.config, H.bind_host, H.bind_port = cfg, a.host, a.port
    s = ThreadingHTTPServer((a.host, a.port), H)
    print(f"[hub] listening on http://{a.host}:{a.port}")
    print(f"[hub] config: {cfg}")
    try: s.serve_forever()
    except KeyboardInterrupt: pass
    finally: s.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
