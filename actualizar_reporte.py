#!/usr/bin/env python3
"""
Unifica descarga de Alaric + generacion del reporte HTML.
Un solo comando para actualizar todo.

Uso:
  python3 actualizar_reporte.py                 # Descarga mes actual + genera + abre
  python3 actualizar_reporte.py --no-browser    # Sin abrir navegador
  python3 actualizar_reporte.py --all           # Descarga todos los meses historicos
  python3 actualizar_reporte.py YYYY-MM         # Solo un mes especifico
  python3 actualizar_reporte.py --serve         # Modo servidor local (tags auto-save)
"""

import os
import sys
import subprocess
import webbrowser
import json
from http.server import HTTPServer, SimpleHTTPRequestHandler

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

DOWNLOADER = os.path.join(SCRIPT_DIR, "download_alaric.py")
GENERATOR = os.path.join(SCRIPT_DIR, "generate_report.py")
REPORT_HTML = os.path.join(SCRIPT_DIR, "trading_report.html")
TAGS_FILE = os.path.join(SCRIPT_DIR, "tags.json")


class TagServerHandler(SimpleHTTPRequestHandler):
    """Sirve archivos + endpoint /save-tags para guardar tags automaticamente."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=SCRIPT_DIR, **kwargs)

    def do_POST(self):
        if self.path == '/save-tags':
            try:
                content_length = int(self.headers.get('Content-Length', 0))
                body = self.rfile.read(content_length)
                tags_data = json.loads(body)
                with open(TAGS_FILE, 'w', encoding='utf-8') as f:
                    json.dump(tags_data, f, indent=2, ensure_ascii=False)
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'ok': True}).encode())
                print(f"  Tags guardados: {len(tags_data)} trades")
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'ok': False, 'error': str(e)}).encode())
                print(f"  Error guardando tags: {e}")
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        # Silenciar logs HTTP (solo mostrar POST /save-tags)
        if 'POST' in str(args):
            super().log_message(format, *args)


def run_server(port=8765):
    """Inicia servidor HTTP local para auto-guardado de tags."""
    print(f"\n  Servidor local: http://localhost:{port}/trading_report.html")
    print(f"  Los tags se guardan automaticamente al pulsar 'Save Tags'.")
    print(f"  Presiona Ctrl+C para detener el servidor.\n")

    server = HTTPServer(('localhost', port), TagServerHandler)
    try:
        webbrowser.open(f"http://localhost:{port}/trading_report.html")
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor detenido.")
        server.shutdown()


def main():
    no_browser = "--no-browser" in sys.argv
    serve_mode = "--no-serve" not in sys.argv  # Serve es default
    args = [a for a in sys.argv[1:] if a not in ("--no-browser", "--no-serve", "--serve")]

    # Paso 1: Descargar
    print("=" * 60)
    print("PASO 1/2: Descargando datos de Alaric...")
    print("=" * 60)

    py_cmd = [sys.executable, DOWNLOADER]
    if args:
        py_cmd.extend(args)

    result = subprocess.run(py_cmd, cwd=SCRIPT_DIR)
    if result.returncode != 0:
        print("\n[ERROR] Fallo la descarga. Abortando.")
        sys.exit(1)

    # Paso 2: Generar reporte
    print("\n" + "=" * 60)
    print("PASO 2/2: Generando reporte HTML...")
    print("=" * 60)

    result = subprocess.run([sys.executable, GENERATOR], cwd=SCRIPT_DIR)
    if result.returncode != 0:
        print("\n[ERROR] Fallo la generacion del reporte.")
        sys.exit(1)

    # Paso 3: Abrir
    if not no_browser and os.path.exists(REPORT_HTML):
        if serve_mode:
            print("\n" + "=" * 60)
            print("MODO SERVIDOR: Guardado automatico de tags activado")
            print("=" * 60)
            run_server()
        else:
            url = f"file://{REPORT_HTML}"
            print(f"\nAbriendo {url}...")
            print("(Tags se guardan por descarga — usa modo normal para esto)")
            webbrowser.open(url)

    print("\nListo. Reporte actualizado.")


if __name__ == "__main__":
    main()
