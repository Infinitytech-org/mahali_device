#!/usr/bin/env python3
"""Serveur de streaming caméra pour le Raspberry Pi (module caméra CSI).

Expose, sur le port 8080 :
  - GET /stream    -> flux MJPEG en direct (multipart/x-mixed-replace)
  - GET /snapshot  -> une seule image JPEG

ENCODAGE LOGICIEL : on capture les images via picamera2 (capture_array) puis on
les encode en JPEG avec simplejpeg (fallback Pillow). Cela contourne l'encodeur
MJPEG matériel, capricieux sur certaines versions (rayures verticales / stride).
Un peu plus de CPU, largement suffisant pour une caméra de serre (quelques FPS).

Réglages via variables d'environnement :
    MAHALI_CAMERA_PORT   (défaut 8080)
    MAHALI_CAMERA_WIDTH  (défaut 1280)
    MAHALI_CAMERA_HEIGHT (défaut 720)
    MAHALI_CAMERA_FPS    (défaut 8)
    MAHALI_CAMERA_QUALITY(défaut 70)
"""

import logging
import os
import socketserver
import threading
import time
from http import server
from threading import Condition

from picamera2 import Picamera2

logger = logging.getLogger("mahali.pi.camera")

PORT = int(os.environ.get("MAHALI_CAMERA_PORT", "8080"))
WIDTH = int(os.environ.get("MAHALI_CAMERA_WIDTH", "1280"))
HEIGHT = int(os.environ.get("MAHALI_CAMERA_HEIGHT", "720"))
FPS = int(os.environ.get("MAHALI_CAMERA_FPS", "8"))
QUALITY = int(os.environ.get("MAHALI_CAMERA_QUALITY", "70"))


class StreamingOutput:
    """Garde la dernière image JPEG et réveille les clients HTTP."""

    def __init__(self):
        self.frame = None
        self.condition = Condition()

    def set(self, buf):
        with self.condition:
            self.frame = buf
            self.condition.notify_all()

    def latest(self):
        with self.condition:
            self.condition.wait()
            return self.frame


output = StreamingOutput()


def _encode(arr) -> bytes:
    """Encode un tableau (BGR, tel que renvoyé par picamera2 'RGB888') en JPEG."""
    try:
        import simplejpeg

        return simplejpeg.encode_jpeg(arr, quality=QUALITY, colorspace="BGR")
    except Exception:  # noqa: BLE001 - fallback Pillow
        import io

        from PIL import Image

        buf = io.BytesIO()
        Image.fromarray(arr[:, :, ::-1]).save(buf, format="JPEG", quality=QUALITY)
        return buf.getvalue()


def _capture_loop(picam2) -> None:
    period = 1.0 / max(1, FPS)
    while True:
        try:
            arr = picam2.capture_array()
            output.set(_encode(arr))
        except Exception:  # noqa: BLE001 - ne jamais tuer la boucle
            logger.exception("Erreur capture caméra")
            time.sleep(1)
        time.sleep(period)


class Handler(server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path in ("/", "/stream", "/stream.mjpg"):
            self.send_response(200)
            self.send_header("Age", "0")
            self.send_header("Cache-Control", "no-cache, private")
            self.send_header("Pragma", "no-cache")
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=FRAME")
            self.end_headers()
            try:
                while True:
                    frame = output.latest()
                    if not frame:
                        continue
                    self.wfile.write(b"--FRAME\r\n")
                    self.wfile.write(b"Content-Type: image/jpeg\r\n")
                    self.wfile.write(f"Content-Length: {len(frame)}\r\n\r\n".encode())
                    self.wfile.write(frame)
                    self.wfile.write(b"\r\n")
            except (BrokenPipeError, ConnectionResetError):
                pass
        elif self.path in ("/snapshot", "/snapshot.jpg", "/capture"):
            frame = output.latest()
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(frame or b"")))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            if frame:
                self.wfile.write(frame)
        else:
            self.send_error(404)
            self.end_headers()


class StreamingServer(socketserver.ThreadingMixIn, server.HTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def main():
    logging.basicConfig(level=logging.INFO)
    picam2 = Picamera2()
    # RGB888 = tableau 3 canaux exploitable directement ; pas d'encodeur matériel.
    picam2.configure(picam2.create_video_configuration(main={"size": (WIDTH, HEIGHT), "format": "RGB888"}))
    picam2.start()
    threading.Thread(target=_capture_loop, args=(picam2,), daemon=True).start()
    logger.info("Caméra démarrée (encodage logiciel) — /stream et /snapshot sur le port %s (%sx%s @ %sfps).",
                PORT, WIDTH, HEIGHT, FPS)
    try:
        StreamingServer(("", PORT), Handler).serve_forever()
    finally:
        picam2.stop()


if __name__ == "__main__":
    main()
