"""Minimal local web UI: upload a photo once, then tweak preset/intensity live.

Runs entirely on localhost, no data leaves the machine. Thin wrapper around
the same auto_enhance/apply_preset functions the CLI uses. The decoded image
and its base auto-enhanced version are kept server-side in memory, keyed by
an id handed back to the browser. Short-lived image URLs serve encoded previews
without embedding base64 in JSON, and changing preset/intensity re-runs only
the preset step instead of re-uploading the file.
"""

from collections import OrderedDict
from io import BytesIO
import os
from pathlib import Path
import threading
from time import perf_counter
import uuid

import cv2
import numpy as np
from flask import Flask, jsonify, render_template, request, send_file, url_for
from PIL import Image, UnidentifiedImageError
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.utils import secure_filename

from photo_enhance.auto_levels import auto_enhance
from photo_enhance.imageio_utils import UnsupportedImageError, load_bgr_bytes
from photo_enhance.presets import apply_preset_blended, list_preset_choices, load_preset

app = Flask(__name__)

MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20MB
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES
MAX_DECODED_PIXELS = 40_000_000
MAX_IMAGE_DIMENSION = 12_000
FILTER_THUMBNAIL_MAX_DIMENSION = 320

MAX_SESSIONS = 20
_sessions: "OrderedDict[str, dict]" = OrderedDict()
_sessions_lock = threading.Lock()


def _store_session(
    enhanced: np.ndarray,
    *,
    before_jpeg: bytes,
    result_jpeg: bytes,
    download_stem: str,
    source_format: str,
    details: dict,
) -> str:
    session_id = uuid.uuid4().hex
    with _sessions_lock:
        _sessions[session_id] = {
            "enhanced": enhanced,
            "before_jpeg": before_jpeg,
            "result_jpeg": result_jpeg,
            "result_id": uuid.uuid4().hex,
            "download_stem": download_stem,
            "download_name": f"{download_stem}_enhanced.jpg",
            "source_format": source_format,
            "details": details,
            "preset": None,
            "intensity": 100,
            "revision": 0,
        }
        _sessions.move_to_end(session_id)
        while len(_sessions) > MAX_SESSIONS:
            _sessions.popitem(last=False)
    return session_id


def _get_session(session_id: str) -> dict | None:
    with _sessions_lock:
        session = _sessions.get(session_id)
        if session is not None:
            _sessions.move_to_end(session_id)
            return session.copy()
        return None


def _bgr_to_jpeg_bytes(img_bgr: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".jpg", img_bgr, [cv2.IMWRITE_JPEG_QUALITY, 90])
    if not ok:
        raise ValueError("Failed to encode image")
    return buf.tobytes()


def _filter_thumbnail(enhanced: np.ndarray, preset_name: str | None) -> bytes:
    """Render a small representative preview without grading the full image again."""
    height, width = enhanced.shape[:2]
    scale = min(1.0, FILTER_THUMBNAIL_MAX_DIMENSION / max(height, width))
    if scale < 1.0:
        thumbnail = cv2.resize(
            enhanced,
            (max(1, round(width * scale)), max(1, round(height * scale))),
            interpolation=cv2.INTER_AREA,
        )
    else:
        thumbnail = enhanced.copy()

    if preset_name:
        thumbnail = apply_preset_blended(thumbnail, load_preset(preset_name), 1.0)
    return _bgr_to_jpeg_bytes(thumbnail)


def _session_payload(session_id: str, session: dict) -> dict:
    result_url = url_for(
        "session_image",
        session_id=session_id,
        kind="result",
        v=session["result_id"],
    )
    return {
        "session_id": session_id,
        "before": url_for("session_image", session_id=session_id, kind="before"),
        "after": result_url,
        "download_url": url_for(
            "session_image",
            session_id=session_id,
            kind="result",
            v=session["result_id"],
            download=1,
        ),
        "download_name": session["download_name"],
        "details": session["details"],
        "preset": session["preset"],
        "intensity": session["intensity"],
        "revision": session["revision"],
    }


@app.errorhandler(RequestEntityTooLarge)
def upload_too_large(_error):
    return jsonify(error=f"Photo is too large. Maximum upload size is {MAX_UPLOAD_BYTES // (1024 * 1024)} MB."), 413


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html", presets=list_preset_choices())


@app.route("/sessions/<session_id>", methods=["GET"])
def session_state(session_id: str):
    session = _get_session(session_id)
    if session is None:
        return jsonify(error="Session expired or not found."), 404
    return jsonify(_session_payload(session_id, session))


@app.route("/sessions/<session_id>/images/<kind>", methods=["GET"])
def session_image(session_id: str, kind: str):
    session = _get_session(session_id)
    if session is None:
        return jsonify(error="Session expired or not found."), 404

    if kind == "before":
        jpeg = session["before_jpeg"]
        download_name = f"{session['download_stem']}_original.jpg"
    elif kind == "result":
        if request.args.get("v") != session["result_id"]:
            return jsonify(error="Image result expired."), 404
        jpeg = session["result_jpeg"]
        download_name = session["download_name"]
    else:
        return jsonify(error="Image not found."), 404

    response = send_file(
        BytesIO(jpeg),
        mimetype="image/jpeg",
        as_attachment=request.args.get("download") == "1",
        download_name=download_name,
    )
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.route("/sessions/<session_id>/presets/<preset_name>/thumbnail", methods=["GET"])
def preset_thumbnail(session_id: str, preset_name: str):
    session = _get_session(session_id)
    if session is None:
        return jsonify(error="Session expired or not found."), 404

    selected_preset = None if preset_name == "auto" else preset_name
    try:
        jpeg = _filter_thumbnail(session["enhanced"], selected_preset)
    except ValueError as exc:
        return jsonify(error=str(exc)), 404
    except cv2.error:
        return jsonify(error="Could not render filter preview."), 422

    response = send_file(BytesIO(jpeg), mimetype="image/jpeg")
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.route("/upload", methods=["POST"])
def upload():
    started_at = perf_counter()
    file = request.files.get("photo")
    if file is None or file.filename == "":
        return jsonify(error="Choose a photo first."), 400

    try:
        encoded = file.read()
    except OSError:
        return jsonify(error="Could not read the uploaded photo."), 400

    try:
        img, metadata = load_bgr_bytes(
            encoded,
            max_pixels=MAX_DECODED_PIXELS,
            max_dimension=MAX_IMAGE_DIMENSION,
        )
    except UnsupportedImageError as exc:
        return jsonify(error=str(exc)), 400
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        return jsonify(error="Could not read that file as an image."), 400

    try:
        enhanced = auto_enhance(img)
    except (ValueError, cv2.error):
        return jsonify(error="Could not enhance that image."), 422
    safe_name = secure_filename(file.filename)
    download_stem = Path(safe_name).stem or "photo"
    source_format = metadata.source_format or "Unknown"
    try:
        before_jpeg = _bgr_to_jpeg_bytes(img)
        result_jpeg = _bgr_to_jpeg_bytes(enhanced)
    except (ValueError, cv2.error):
        return jsonify(error="Could not encode the enhanced preview."), 500

    height, width = img.shape[:2]
    details = {
        "width": width,
        "height": height,
        "source_format": source_format,
        "output_format": "JPEG preview",
        "processing_ms": round((perf_counter() - started_at) * 1000),
    }
    session_id = _store_session(
        enhanced,
        before_jpeg=before_jpeg,
        result_jpeg=result_jpeg,
        download_stem=download_stem,
        source_format=source_format,
        details=details,
    )
    return jsonify(_session_payload(session_id, _get_session(session_id)))


@app.route("/apply", methods=["POST"])
def apply():
    started_at = perf_counter()
    data = request.get_json(silent=True) or {}
    session_id = data.get("session_id")
    preset_name = data.get("preset") or None
    intensity = data.get("intensity", 100)
    requested_revision = data.get("revision")

    session = _get_session(session_id) if session_id else None
    if session is None:
        return jsonify(error="Session expired or not found. Please re-upload the photo."), 400

    try:
        intensity_percent = max(0, min(100, int(intensity)))
        intensity_fraction = intensity_percent / 100.0
    except (TypeError, ValueError):
        return jsonify(error="Invalid intensity value."), 400
    if requested_revision is not None:
        try:
            requested_revision = int(requested_revision)
        except (TypeError, ValueError):
            return jsonify(error="Invalid revision value."), 400
        if requested_revision < 0:
            return jsonify(error="Invalid revision value."), 400
    else:
        requested_revision = session["revision"] + 1

    enhanced = session["enhanced"]
    if preset_name:
        try:
            preset = load_preset(preset_name)
        except ValueError as exc:
            return jsonify(error=str(exc)), 400
        try:
            result = apply_preset_blended(enhanced, preset, intensity_fraction)
        except (ValueError, cv2.error):
            return jsonify(error="Could not apply that filter."), 422
    else:
        result = enhanced

    try:
        result_jpeg = _bgr_to_jpeg_bytes(result)
    except (ValueError, cv2.error):
        return jsonify(error="Could not encode the filtered preview."), 500
    preset_suffix = f"_{preset_name}" if preset_name else ""
    height, width = result.shape[:2]
    details = {
        "width": width,
        "height": height,
        "source_format": session["source_format"],
        "output_format": "JPEG preview",
        "processing_ms": round((perf_counter() - started_at) * 1000),
    }
    with _sessions_lock:
        current = _sessions.get(session_id)
        if current is None:
            return jsonify(error="Session expired or not found. Please re-upload the photo."), 400
        if requested_revision < current["revision"]:
            return jsonify(error="A newer filter request already completed.", stale=True), 409
        current.update(
            result_jpeg=result_jpeg,
            result_id=uuid.uuid4().hex,
            download_name=f"{current['download_stem']}_enhanced{preset_suffix}.jpg",
            details=details,
            preset=preset_name,
            intensity=intensity_percent,
            revision=requested_revision,
        )
        _sessions.move_to_end(session_id)
        payload = _session_payload(session_id, current)
    return jsonify(payload)


def main():
    debug = os.environ.get("PHOTO_ENHANCE_DEBUG", "").strip().lower() in ("1", "true", "yes")
    app.run(host="127.0.0.1", port=5050, debug=debug)


if __name__ == "__main__":
    main()
