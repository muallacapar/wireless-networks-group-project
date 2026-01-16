#!/usr/bin/env python3
import os, re, json, signal, subprocess, time
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT_TX = os.environ.get("PORT_TX", "/dev/ttyUSB0")
BAUD    = os.environ.get("BAUD", "115200")

TEMPLATE = "advertiser_duty_180.py"
RUNFILE  = "_tx_run.py"

proc = None
current_level = None

def make_runfile(level: str):
    with open(TEMPLATE, "r", encoding="utf-8", errors="ignore") as f:
        s = f.read()

    # TX_LEVEL değiştir
    s = re.sub(r'^\s*TX_LEVEL\s*=\s*".*?"\s*$', f'TX_LEVEL = "{level}"', s, flags=re.M)
    # demo için uzun süre
    s = re.sub(r'^\s*TOTAL_S\s*=\s*\d+.*$', 'TOTAL_S  = 999999  # demo', s, flags=re.M)

    with open(RUNFILE, "w", encoding="utf-8") as f:
        f.write(s)

def stop_current():
    global proc
    if proc and proc.poll() is None:
        try:
            proc.send_signal(signal.SIGINT)
            time.sleep(0.2)
        except Exception:
            pass
        try:
            proc.kill()
        except Exception:
            pass
    proc = None

def start_level(level: str):
    global proc, current_level
    level = level.upper().strip()
    if level not in ("L0", "L1", "L2"):
        raise ValueError("Level must be L0/L1/L2")

    # aynı level çalışıyorsa dokunma
    if current_level == level and proc and proc.poll() is None:
        print(f"[TX_SWITCHER] already running {level}")
        return

    stop_current()
    make_runfile(level)

    cmd = ["ampy", "--port", PORT_TX, "--baud", BAUD, "run", "--no-output", RUNFILE]
    print(f"[TX_SWITCHER] starting {level} -> {' '.join(cmd)}")
    proc = subprocess.Popen(cmd)
    current_level = level

class Handler(BaseHTTPRequestHandler):
    def _send_json(self, code, payload):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode("utf-8"))

    def do_POST(self):
        if self.path != "/set_level":
            return self._send_json(404, {"ok": False, "error": "not_found"})

        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length).decode("utf-8")
            data = json.loads(body)
            level = data.get("level", "").upper().strip()

            print("[HTTP] set_level ->", level)
            start_level(level)
            self._send_json(200, {"ok": True, "level": level})
        except Exception as e:
            self._send_json(400, {"ok": False, "error": str(e)})

def main():
    host, port = "0.0.0.0", 8080
    print("[TX_SWITCHER] Template:", TEMPLATE)
    print("[TX_SWITCHER] PORT_TX:", PORT_TX, " BAUD:", BAUD)
    print(f"[TX_SWITCHER] Listening http://{host}:{port}/set_level")
    HTTPServer((host, port), Handler).serve_forever()

if __name__ == "__main__":
    main()
