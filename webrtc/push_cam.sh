#!/usr/bin/env bash
# Pousseur caméra -> mediamtx (WebRTC) pour Mahali.
# Lit le flux MJPEG de l'ESP32-CAM, transcode en H.264 faible latence, et publie
# en RTSP (sortant) vers le serveur mediamtx public. Aucun port a ouvrir cote serre.
#
# Config via /etc/mahali/webrtc.env (voir mahali-webrtc-push.service) :
#   ESP32_STREAM_URL   ex: http://mahali-cam.local:81/stream   (MJPEG)
#   MEDIAMTX_RTSP_URL  ex: rtsp://PUBLISH_USER:PUBLISH_PASS@NOUVEAU_SERVEUR:8554/serre-s001
#   FPS                ex: 12      (images/s ; bas = moins de CPU et de data)
#   BITRATE            ex: 700k    (debit video cible)
#   GOP                ex: 24      (intervalle keyframe ; ~2s a 12 fps)
set -euo pipefail

ESP32_STREAM_URL="${ESP32_STREAM_URL:?ESP32_STREAM_URL requis}"
MEDIAMTX_RTSP_URL="${MEDIAMTX_RTSP_URL:?MEDIAMTX_RTSP_URL requis}"
FPS="${FPS:-12}"
BITRATE="${BITRATE:-700k}"
GOP="${GOP:-24}"

exec ffmpeg -hide_banner -loglevel warning \
  -fflags nobuffer -flags low_delay \
  -f mjpeg -use_wallclock_as_timestamps 1 -i "$ESP32_STREAM_URL" \
  -c:v libx264 -preset ultrafast -tune zerolatency -profile:v baseline \
  -pix_fmt yuv420p -r "$FPS" -g "$GOP" -keyint_min "$GOP" \
  -b:v "$BITRATE" -maxrate "$BITRATE" -bufsize "$BITRATE" \
  -an \
  -f rtsp -rtsp_transport tcp "$MEDIAMTX_RTSP_URL"
