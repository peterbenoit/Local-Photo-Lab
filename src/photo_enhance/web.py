"""Minimal local web UI: upload a photo once, then tweak preset/intensity live.

Runs entirely on localhost, no data leaves the machine. Thin wrapper around
the same auto_enhance/apply_preset functions the CLI uses. The decoded image
and its base auto-enhanced version are kept server-side in memory, keyed by
an id handed back to the browser. Short-lived image URLs serve encoded previews
without embedding base64 in JSON, and changing preset/intensity re-runs only
the preset step instead of re-uploading the file.
"""

import os
import threading
import uuid
from collections import OrderedDict
from dataclasses import asdict
from io import BytesIO
from pathlib import Path
from time import perf_counter

import cv2
import numpy as np
from flask import Flask, jsonify, render_template, request, send_file, url_for
from PIL import Image, UnidentifiedImageError
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.utils import secure_filename

from photo_enhance.auto_levels import AutoSettings
from photo_enhance.comparison import build_comparison
from photo_enhance.imageio_utils import UnsupportedImageError, load_bgr_bytes
from photo_enhance.nature import NatureSettings, apply_nature_adjustments
from photo_enhance.pipeline import EnhancementError, EnhancementOptions, enhance_image
from photo_enhance.presets import (
    apply_preset_blended,
    apply_preset_with_defaults,
    list_preset_choices,
    load_preset,
)

app = Flask(__name__)
app.config["PRESET_DIR"] = os.environ.get("PHOTO_ENHANCE_PRESET_DIR") or None

MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20MB
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES
MAX_DECODED_PIXELS = 40_000_000
MAX_IMAGE_DIMENSION = 12_000
FILTER_THUMBNAIL_MAX_DIMENSION = 320
COMPARISON_PANEL_MAX_DIMENSION = 2400

try:
    MAX_SESSIONS = max(1, min(100, int(os.environ.get("PHOTO_ENHANCE_MAX_SESSIONS", "20"))))
except ValueError:
    MAX_SESSIONS = 20
app.config["MAX_SESSIONS"] = MAX_SESSIONS
_sessions: "OrderedDict[str, dict]" = OrderedDict()
_sessions_lock = threading.Lock()


def _store_session(
    source: np.ndarray,
    *,
    filter_base: np.ndarray,
    auto_settings: AutoSettings,
    auto_metrics: dict,
    nature_settings: NatureSettings,
    before_jpeg: bytes,
    result_jpeg: bytes,
    download_stem: str,
    source_format: str,
    details: dict,
) -> str:
    session_id = uuid.uuid4().hex
    with _sessions_lock:
        _sessions[session_id] = {
            "source": source,
            "filter_base": filter_base,
            "before_jpeg": before_jpeg,
            "result_jpeg": result_jpeg,
            "result_id": uuid.uuid4().hex,
            "download_stem": download_stem,
            "download_name": f"{download_stem}_enhanced.jpg",
            "source_format": source_format,
            "details": details,
            "preset": None,
            "intensity": 100,
            "temperature": 0,
            "fade": 0,
            "vignette": 0,
            "grain": 0,
            "auto_white_balance": round(auto_settings.white_balance * 100),
            "auto_levels": round(auto_settings.levels * 100),
            "auto_local_contrast": round(auto_settings.local_contrast * 100),
            "shadows": round(nature_settings.shadows * 100),
            "highlights": round(nature_settings.highlights * 100),
            "vibrance": round(nature_settings.vibrance * 100),
            "detail": round(nature_settings.detail * 100),
            "denoise": round(nature_settings.denoise * 100),
            "auto_recommendation": {
                "auto_white_balance": round(auto_settings.white_balance * 100),
                "auto_levels": round(auto_settings.levels * 100),
                "auto_local_contrast": round(auto_settings.local_contrast * 100),
                "shadows": round(nature_settings.shadows * 100),
                "highlights": round(nature_settings.highlights * 100),
                "vibrance": round(nature_settings.vibrance * 100),
                "detail": round(nature_settings.detail * 100),
                "denoise": round(nature_settings.denoise * 100),
            },
            "auto_metrics": auto_metrics,
            "grain_seed": uuid.uuid4().int & 0xFFFFFFFF,
            "revision": 0,
        }
        _sessions.move_to_end(session_id)
        while len(_sessions) > app.config["MAX_SESSIONS"]:
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


def _filter_thumbnail(
    enhanced: np.ndarray,
    preset_name: str | None,
    auto_recommendation: dict,
    preset_dir: Path | None = None,
) -> bytes:
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
        preset = load_preset(preset_name, preset_dir)
        if preset.get("defaults"):
            thumbnail = apply_preset_with_defaults(thumbnail, preset)
            return _bgr_to_jpeg_bytes(thumbnail)
        thumbnail = apply_preset_blended(thumbnail, preset, 1.0)
    thumbnail = apply_nature_adjustments(
        thumbnail,
        shadows=auto_recommendation["shadows"] / 100.0,
        highlights=auto_recommendation["highlights"] / 100.0,
        vibrance=auto_recommendation["vibrance"] / 100.0,
        detail=auto_recommendation["detail"] / 100.0,
        denoise=auto_recommendation["denoise"] / 100.0,
    )
    return _bgr_to_jpeg_bytes(thumbnail)


def _comparison_jpeg(before_jpeg: bytes, after_jpeg: bytes) -> bytes:
    """Build a bounded, labeled side-by-side comparison JPEG."""
    before = cv2.imdecode(np.frombuffer(before_jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
    after = cv2.imdecode(np.frombuffer(after_jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
    if before is None or after is None:
        raise ValueError("Could not decode comparison images")
    canvas = build_comparison(
        before,
        after,
        max_panel_dimension=COMPARISON_PANEL_MAX_DIMENSION,
    )
    return _bgr_to_jpeg_bytes(canvas)


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
        "comparison_url": url_for(
            "session_comparison",
            session_id=session_id,
            v=session["result_id"],
        ),
        "comparison_name": f"{session['download_stem']}_before-after.jpg",
        "details": session["details"],
        "preset": session["preset"],
        "intensity": session["intensity"],
        "temperature": session["temperature"],
        "fade": session["fade"],
        "vignette": session["vignette"],
        "grain": session["grain"],
        "auto_white_balance": session["auto_white_balance"],
        "auto_levels": session["auto_levels"],
        "auto_local_contrast": session["auto_local_contrast"],
        "shadows": session["shadows"],
        "highlights": session["highlights"],
        "vibrance": session["vibrance"],
        "detail": session["detail"],
        "denoise": session["denoise"],
        "auto_recommendation": session["auto_recommendation"],
        "auto_metrics": session["auto_metrics"],
        "revision": session["revision"],
    }


def _recent_session_payload(session_id: str, session: dict) -> dict:
    preset_name = session["preset"] or "Auto"
    return {
        "session_id": session_id,
        "name": session["download_stem"],
        "look": preset_name.replace("_", " ").title(),
        "dimensions": (f"{session['details']['width']} × {session['details']['height']} px"),
        "thumbnail": url_for(
            "session_image",
            session_id=session_id,
            kind="result",
            v=session["result_id"],
        ),
    }


@app.errorhandler(RequestEntityTooLarge)
def upload_too_large(_error):
    return jsonify(
        error=f"Photo is too large. Maximum upload size is {MAX_UPLOAD_BYTES // (1024 * 1024)} MB."
    ), 413


@app.route("/", methods=["GET"])
def index():
    preset_dir = Path(app.config["PRESET_DIR"]) if app.config["PRESET_DIR"] else None
    presets = list_preset_choices(preset_dir)
    return render_template(
        "index.html",
        presets=presets,
        nature_presets=[preset for preset in presets if preset["category"] == "nature"],
        creative_presets=[preset for preset in presets if preset["category"] != "nature"],
        session_limit=app.config["MAX_SESSIONS"],
    )


@app.route("/sessions", methods=["GET", "DELETE"])
def recent_sessions():
    with _sessions_lock:
        if request.method == "DELETE":
            removed = len(_sessions)
            _sessions.clear()
            return jsonify(removed=removed, sessions=[])
        sessions = [
            _recent_session_payload(session_id, session)
            for session_id, session in reversed(_sessions.items())
        ]
    return jsonify(limit=app.config["MAX_SESSIONS"], sessions=sessions)


@app.route("/sessions/<session_id>", methods=["GET", "DELETE"])
def session_state(session_id: str):
    if request.method == "DELETE":
        with _sessions_lock:
            removed = _sessions.pop(session_id, None)
        if removed is None:
            return jsonify(error="Session expired or not found."), 404
        return jsonify(removed=session_id)
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
    preset_dir = Path(app.config["PRESET_DIR"]) if app.config["PRESET_DIR"] else None
    try:
        jpeg = _filter_thumbnail(
            session["filter_base"],
            selected_preset,
            session["auto_recommendation"],
            preset_dir,
        )
    except ValueError as exc:
        return jsonify(error=str(exc)), 404
    except cv2.error:
        return jsonify(error="Could not render filter preview."), 422

    response = send_file(BytesIO(jpeg), mimetype="image/jpeg")
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.route("/sessions/<session_id>/comparison", methods=["GET"])
def session_comparison(session_id: str):
    session = _get_session(session_id)
    if session is None:
        return jsonify(error="Session expired or not found."), 404
    if request.args.get("v") != session["result_id"]:
        return jsonify(error="Comparison result expired."), 404

    try:
        jpeg = _comparison_jpeg(session["before_jpeg"], session["result_jpeg"])
    except (ValueError, cv2.error):
        return jsonify(error="Could not create comparison image."), 500

    response = send_file(
        BytesIO(jpeg),
        mimetype="image/jpeg",
        as_attachment=True,
        download_name=f"{session['download_stem']}_before-after.jpg",
    )
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
        enhancement = enhance_image(img)
        auto_base = enhancement.auto_image
        enhanced = enhancement.image
    except EnhancementError:
        return jsonify(error="Could not enhance that image."), 422
    safe_name = secure_filename(file.filename or "photo")
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
    filter_height, filter_width = auto_base.shape[:2]
    filter_scale = min(1.0, FILTER_THUMBNAIL_MAX_DIMENSION / max(filter_height, filter_width))
    filter_base = (
        cv2.resize(
            auto_base,
            (
                max(1, round(filter_width * filter_scale)),
                max(1, round(filter_height * filter_scale)),
            ),
            interpolation=cv2.INTER_AREA,
        )
        if filter_scale < 1
        else auto_base.copy()
    )
    session_id = _store_session(
        img,
        filter_base=filter_base,
        auto_settings=enhancement.auto_settings,
        auto_metrics=asdict(enhancement.auto_analysis.metrics),
        nature_settings=enhancement.nature_settings,
        before_jpeg=before_jpeg,
        result_jpeg=result_jpeg,
        download_stem=download_stem,
        source_format=source_format,
        details=details,
    )
    stored_session = _get_session(session_id)
    assert stored_session is not None
    return jsonify(_session_payload(session_id, stored_session))


@app.route("/apply", methods=["POST"])
def apply():
    started_at = perf_counter()
    data = request.get_json(silent=True) or {}
    session_id = data.get("session_id")
    preset_name = data.get("preset") or None
    intensity = data.get("intensity", 100)
    requested_revision = data.get("revision")

    if not isinstance(session_id, str) or not session_id:
        return jsonify(error="Session expired or not found. Please re-upload the photo."), 400
    session = _get_session(session_id)
    if session is None:
        return jsonify(error="Session expired or not found. Please re-upload the photo."), 400
    temperature = data.get("temperature", session["temperature"])
    fade = data.get("fade", session["fade"])
    vignette = data.get("vignette", session["vignette"])
    grain = data.get("grain", session["grain"])
    shadows = data.get("shadows", session["shadows"])
    highlights = data.get("highlights", session["highlights"])
    vibrance = data.get("vibrance", session["vibrance"])
    detail = data.get("detail", session["detail"])
    denoise = data.get("denoise", session["denoise"])
    auto_white_balance = data.get("auto_white_balance", session["auto_white_balance"])
    auto_levels_strength = data.get("auto_levels", session["auto_levels"])
    auto_local_contrast = data.get("auto_local_contrast", session["auto_local_contrast"])

    try:
        intensity_percent = max(0, min(100, int(intensity)))
        temperature_percent = max(-100, min(100, int(temperature)))
        fade_percent = max(0, min(100, int(fade)))
        vignette_percent = max(0, min(100, int(vignette)))
        grain_percent = max(0, min(100, int(grain)))
        shadows_percent = max(0, min(100, int(shadows)))
        highlights_percent = max(0, min(100, int(highlights)))
        vibrance_percent = max(0, min(100, int(vibrance)))
        detail_percent = max(0, min(100, int(detail)))
        denoise_percent = max(0, min(100, int(denoise)))
        auto_white_balance_percent = max(0, min(100, int(auto_white_balance)))
        auto_levels_percent = max(0, min(100, int(auto_levels_strength)))
        auto_local_contrast_percent = max(0, min(100, int(auto_local_contrast)))
        intensity_fraction = intensity_percent / 100.0
    except (TypeError, ValueError):
        return jsonify(error="Invalid adjustment value."), 400
    if requested_revision is not None:
        try:
            requested_revision = int(requested_revision)
        except (TypeError, ValueError):
            return jsonify(error="Invalid revision value."), 400
        if requested_revision < 0:
            return jsonify(error="Invalid revision value."), 400
    else:
        requested_revision = session["revision"] + 1

    auto_settings = AutoSettings(
        white_balance=auto_white_balance_percent / 100.0,
        levels=auto_levels_percent / 100.0,
        local_contrast=auto_local_contrast_percent / 100.0,
    )
    preset = None
    if preset_name:
        preset_dir = Path(app.config["PRESET_DIR"]) if app.config["PRESET_DIR"] else None
        try:
            preset = load_preset(preset_name, preset_dir)
        except ValueError as exc:
            return jsonify(error=str(exc)), 400

    options = EnhancementOptions(
        auto_settings=auto_settings,
        nature_settings=NatureSettings(
            shadows=shadows_percent / 100.0,
            highlights=highlights_percent / 100.0,
            vibrance=vibrance_percent / 100.0,
            detail=detail_percent / 100.0,
            denoise=denoise_percent / 100.0,
        ),
        preset=preset,
        preset_intensity=intensity_fraction,
        temperature=temperature_percent / 100.0,
        fade=fade_percent / 100.0,
        vignette=vignette_percent / 100.0,
        grain=grain_percent / 100.0,
        grain_seed=session["grain_seed"],
    )
    try:
        result = enhance_image(session["source"], options).image
    except EnhancementError as exc:
        messages = {
            "auto": "Could not apply Auto corrections.",
            "preset": "Could not apply that filter.",
            "nature": "Could not apply nature adjustments.",
            "finishing": "Could not apply finishing adjustments.",
        }
        return jsonify(error=messages.get(exc.stage, "Could not enhance that image.")), 422

    try:
        result_jpeg = _bgr_to_jpeg_bytes(result)
    except (ValueError, cv2.error):
        return jsonify(error="Could not encode the filtered preview."), 500
    preset_suffix = f"_{preset_name}" if preset_name else ""
    finish_suffix = ""
    if temperature_percent > 0:
        finish_suffix += "_warm"
    elif temperature_percent < 0:
        finish_suffix += "_cool"
    if fade_percent:
        finish_suffix += "_fade"
    if vignette_percent:
        finish_suffix += "_vignette"
    if grain_percent:
        finish_suffix += "_grain"
    recommended = session["auto_recommendation"]
    if any(
        (
            shadows_percent != recommended["shadows"],
            highlights_percent != recommended["highlights"],
            vibrance_percent != recommended["vibrance"],
            detail_percent != recommended["detail"],
            denoise_percent != recommended["denoise"],
        )
    ):
        finish_suffix += "_nature"
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
            download_name=(
                f"{current['download_stem']}_enhanced{preset_suffix}{finish_suffix}.jpg"
            ),
            details=details,
            preset=preset_name,
            intensity=intensity_percent,
            temperature=temperature_percent,
            fade=fade_percent,
            vignette=vignette_percent,
            grain=grain_percent,
            auto_white_balance=auto_white_balance_percent,
            auto_levels=auto_levels_percent,
            auto_local_contrast=auto_local_contrast_percent,
            shadows=shadows_percent,
            highlights=highlights_percent,
            vibrance=vibrance_percent,
            detail=detail_percent,
            denoise=denoise_percent,
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
