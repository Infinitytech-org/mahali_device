#!/usr/bin/env python3
"""Serveur de streaming caméra pour le Raspberry Pi (module caméra CSI).

Expose, sur le port 8080 :
  - GET /stream    -> flux MJPEG en direct (multipart/x-mixed-replace)
  - GET /snapshot  -> une seule image JPEG

Le backend Mahali PROXIFIE ces URLs (champs `cam_stream_url` /
`cam_snapshot_url` de la serre), donc l'app mobile n'a jamais à joindre le Pi
directement — elle passe par /api/greenhouses/<slug>/camera/stream|snapshot/.

Dépendance : picamera2 (paquet SYSTÈME, pas pip/venv) :
    sudo apt install -y python3-picamera2
Ce script tourne donc avec le python système (/usr/bin/python3), lancé par le
service systemd `mahali-camera`.

Réglages via variables d'environnement :
    MAHALI_CAMERA_PORT   (défaut 8080)
    MAHALI_CAMERA_WIDTH  (défaut 1280)
    MAHALI_CAMERA_HEIGHT (défaut 720)
"""

import io
import logging
import os
import socketserver
from http import server
from threading import Condition

from picamera2 import Picamera2
from picamera2.encoders import MJPEGEncoder, Quality
from picamera2.outputs import FileOutput

logger = logging.getLogger("mahali.pi.camera")

PORT = int(os.environ.get("MAHALI_CAMERA_PORT", "8080"))
WIDTH = int(os.environ.get("MAHALI_CAMERA_WIDTH", "1280"))
HEIGHT = int(os.environ.get("MAHALI_CAMERA_HEIGHT", "720"))


class StreamingOutput(io.BufferedIOBase):
    """Reçoit chaque image JPEG de l'encodeur et réveille les clients HTTP."""

    def __init__(self):
        self.frame = None
        self.condition = Condition()

    def write(self, buf):
        with self.condition:
            self.frame = buf
            self.condition.notify_all()


output = StreamingOutput()


def _latest_frame():
    with output.condition:
        output.condition.wait()
        return output.frame


class Handler(server.BaseHTTPRequestHandler):
    def log_message(self, *args):  # silence les logs d'accès HTTP
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
                    frame = _latest_frame()
                    self.wfile.write(b"--FRAME\r\n")
                    self.wfile.write(b"Content-Type: image/jpeg\r\n")
                    self.wfile.write(f"Content-Length: {len(frame)}\r\n\r\n".encode())
                    self.wfile.write(frame)
                    self.wfile.write(b"\r\n")
            except (BrokenPipeError, ConnectionResetError):
                pass  # le client (le proxy backend) s'est déconnecté
        elif self.path in ("/snapshot", "/snapshot.jpg", "/capture"):
            frame = _latest_frame()
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(frame)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
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
    picam2.configure(picam2.create_video_configuration(main={"size": (WIDTH, HEIGHT)}))
    picam2.start_recording(MJPEGEncoder(), FileOutput(output), Quality.MEDIUM)
    logger.info("Caméra démarrée — /stream et /snapshot sur le port %s (%sx%s).", PORT, WIDTH, HEIGHT)
    try:
        StreamingServer(("", PORT), Handler).serve_forever()
    finally:
        picam2.stop_recording()


if __name__ == "__main__":
    main()
