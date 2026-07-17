import io

import cv2
import numpy as np
from PIL import Image

from photo_enhance.web import app


def _jpeg_bytes() -> bytes:
    img = np.full((16, 16, 3), 130, dtype=np.uint8)
    ok, buf = cv2.imencode(".jpg", img)
    assert ok
    return buf.tobytes()


def _transparent_png_bytes() -> bytes:
    output = io.BytesIO()
    Image.new("RGBA", (16, 16), (100, 120, 140, 100)).save(output, format="PNG")
    return output.getvalue()


def test_index_lists_all_presets():
    client = app.test_client()
    resp = client.get("/")
    assert resp.status_code == 200
    text = resp.get_data(as_text=True)
    for name in (
        "Warm Film",
        "Cool Moody",
        "High Contrast B&amp;W",
        "Faded Vintage",
        "Golden Hour",
        "Teal &amp; Ember",
        "Cross Process",
        "Soft Portrait",
    ):
        assert name in text


def test_index_has_accessible_landmarks_feedback_and_result_controls():
    client = app.test_client()
    text = client.get("/").get_data(as_text=True)

    assert 'class="skip-link" href="#main"' in text
    assert '<main id="main">' in text
    assert 'for="photo-input"' in text
    assert 'aria-describedby="upload-hint error-message"' in text
    assert 'id="error-message" role="alert" tabindex="-1"' in text
    assert 'id="status-message" role="status"' in text
    assert 'id="results-heading" tabindex="-1"' in text
    assert 'id="download-link"' in text


def test_index_has_progressive_dropzone_and_keyboard_comparison_controls():
    client = app.test_client()
    text = client.get("/").get_data(as_text=True)

    assert 'id="upload-dropzone"' in text
    assert "Drop a photo into the darkroom" in text
    assert 'class="filter-radio" type="radio" name="preset"' in text
    assert 'id="comparison-controls" hidden' in text
    assert 'id="slider-view-button" aria-pressed="true"' in text
    assert 'id="side-by-side-button" aria-pressed="false"' in text
    assert 'id="comparison-range" type="range" min="0" max="100" value="50"' in text
    assert 'aria-label="Before and after dividing line"' in text
    assert "clip-path: inset(0 0 0 var(--comparison-position))" in text
    assert "`${position}% original photo and ${100 - position}% enhanced photo visible`" in text
    assert 'id="side-by-side-view"' in text
    assert 'uploadDropzone.addEventListener("drop"' in text
    assert 'photoInput.addEventListener("change"' in text
    assert "Enhance photo" not in text
    assert 'comparisonRange.addEventListener("input"' in text
    assert "async function restoreSession()" in text
    assert 'url.searchParams.set("session", id)' in text
    assert "revision: token" in text


def test_upload_without_file_returns_400():
    client = app.test_client()
    resp = client.post("/upload", data={})
    assert resp.status_code == 400
    assert "error" in resp.get_json()


def test_oversized_upload_returns_friendly_json_error():
    client = app.test_client()
    original_limit = app.config["MAX_CONTENT_LENGTH"]
    app.config["MAX_CONTENT_LENGTH"] = 10
    try:
        resp = client.post(
            "/upload",
            data={"photo": (io.BytesIO(_jpeg_bytes()), "photo.jpg")},
            content_type="multipart/form-data",
        )
    finally:
        app.config["MAX_CONTENT_LENGTH"] = original_limit

    assert resp.status_code == 413
    assert "maximum upload size" in resp.get_json()["error"].lower()


def test_upload_rejects_excessive_decoded_pixels(monkeypatch):
    from photo_enhance import web

    monkeypatch.setattr(web, "MAX_DECODED_PIXELS", 100)
    client = app.test_client()
    resp = client.post(
        "/upload",
        data={"photo": (io.BytesIO(_jpeg_bytes()), "photo.jpg")},
        content_type="multipart/form-data",
    )

    assert resp.status_code == 400
    assert "decoded pixels" in resp.get_json()["error"].lower()


def test_upload_rejects_transparency_instead_of_flattening_it():
    client = app.test_client()
    resp = client.post(
        "/upload",
        data={"photo": (io.BytesIO(_transparent_png_bytes()), "photo.png")},
        content_type="multipart/form-data",
    )

    assert resp.status_code == 400
    assert "alpha channel" in resp.get_json()["error"].lower()


def test_upload_returns_session_id_and_images():
    client = app.test_client()
    data = {"photo": (io.BytesIO(_jpeg_bytes()), "photo.jpg")}
    resp = client.post("/upload", data=data, content_type="multipart/form-data")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["session_id"]
    assert body["before"].startswith(f"/sessions/{body['session_id']}/images/before")
    assert body["after"].startswith(f"/sessions/{body['session_id']}/images/result?v=")
    assert body["download_url"].endswith("&download=1")
    assert b"base64" not in resp.data
    assert len(resp.data) < 2_000
    assert body["download_name"] == "photo_enhanced.jpg"
    assert body["details"]["height"] == 16
    assert body["details"]["width"] == 16
    assert body["details"]["source_format"] == "JPEG"
    assert body["details"]["output_format"] == "JPEG preview"
    assert body["details"]["processing_ms"] >= 0


def test_upload_sanitizes_download_filename():
    client = app.test_client()
    data = {"photo": (io.BytesIO(_jpeg_bytes()), "../../family photo.jpg")}
    resp = client.post("/upload", data=data, content_type="multipart/form-data")

    assert resp.status_code == 200
    assert resp.get_json()["download_name"] == "family_photo_enhanced.jpg"


def test_upload_enhancement_failure_returns_friendly_error(monkeypatch):
    from photo_enhance import web

    def fail_enhancement(_image):
        raise ValueError("simulated pipeline failure")

    monkeypatch.setattr(web, "auto_enhance", fail_enhancement)
    client = app.test_client()
    resp = client.post(
        "/upload",
        data={"photo": (io.BytesIO(_jpeg_bytes()), "photo.jpg")},
        content_type="multipart/form-data",
    )

    assert resp.status_code == 422
    assert resp.get_json()["error"] == "Could not enhance that image."


def test_upload_encoding_failure_returns_friendly_error(monkeypatch):
    from photo_enhance import web

    def fail_encoding(_image):
        raise ValueError("simulated encoding failure")

    monkeypatch.setattr(web, "_bgr_to_jpeg_bytes", fail_encoding)
    client = app.test_client()
    resp = client.post(
        "/upload",
        data={"photo": (io.BytesIO(_jpeg_bytes()), "photo.jpg")},
        content_type="multipart/form-data",
    )

    assert resp.status_code == 500
    assert resp.get_json()["error"] == "Could not encode the enhanced preview."


def test_apply_without_prior_upload_returns_400():
    client = app.test_client()
    resp = client.post("/apply", json={"session_id": "does-not-exist", "preset": "warm_film", "intensity": 100})
    assert resp.status_code == 400
    assert "error" in resp.get_json()


def test_apply_with_valid_session_and_preset_returns_image():
    client = app.test_client()
    data = {"photo": (io.BytesIO(_jpeg_bytes()), "photo.jpg")}
    upload_resp = client.post("/upload", data=data, content_type="multipart/form-data")
    session_id = upload_resp.get_json()["session_id"]

    resp = client.post("/apply", json={"session_id": session_id, "preset": "warm_film", "intensity": 50})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["after"].startswith(f"/sessions/{session_id}/images/result?v=")
    assert body["download_name"] == "photo_enhanced_warm_film.jpg"
    assert body["details"]["source_format"] == "JPEG"
    assert body["details"]["width"] == 16
    assert body["details"]["height"] == 16


def test_apply_with_unknown_preset_returns_400():
    client = app.test_client()
    data = {"photo": (io.BytesIO(_jpeg_bytes()), "photo.jpg")}
    upload_resp = client.post("/upload", data=data, content_type="multipart/form-data")
    session_id = upload_resp.get_json()["session_id"]

    resp = client.post("/apply", json={"session_id": session_id, "preset": "not_a_real_preset", "intensity": 100})
    assert resp.status_code == 400
    assert "error" in resp.get_json()


def test_apply_without_preset_returns_base_enhanced_image():
    client = app.test_client()
    data = {"photo": (io.BytesIO(_jpeg_bytes()), "photo.jpg")}
    upload_resp = client.post("/upload", data=data, content_type="multipart/form-data")
    session_id = upload_resp.get_json()["session_id"]

    resp = client.post("/apply", json={"session_id": session_id, "preset": "", "intensity": 100})
    assert resp.status_code == 200
    assert resp.get_json()["after"].startswith(f"/sessions/{session_id}/images/result?v=")


def test_session_image_urls_serve_jpeg_and_download_headers():
    client = app.test_client()
    upload = client.post(
        "/upload",
        data={"photo": (io.BytesIO(_jpeg_bytes()), "family photo.jpg")},
        content_type="multipart/form-data",
    ).get_json()

    before = client.get(upload["before"])
    result = client.get(upload["after"])
    download = client.get(upload["download_url"])

    assert before.status_code == 200
    assert result.status_code == 200
    assert before.content_type == "image/jpeg"
    assert result.data.startswith(b"\xff\xd8")
    assert result.headers["Cache-Control"] == "private, no-store"
    assert result.headers["X-Content-Type-Options"] == "nosniff"
    assert "attachment" in download.headers["Content-Disposition"]
    assert "family_photo_enhanced.jpg" in download.headers["Content-Disposition"]


def test_session_filter_thumbnails_render_auto_and_preset_looks():
    client = app.test_client()
    upload = client.post(
        "/upload",
        data={"photo": (io.BytesIO(_jpeg_bytes()), "photo.jpg")},
        content_type="multipart/form-data",
    ).get_json()
    session_id = upload["session_id"]

    auto = client.get(f"/sessions/{session_id}/presets/auto/thumbnail")
    filtered = client.get(f"/sessions/{session_id}/presets/teal_ember/thumbnail")
    unknown = client.get(f"/sessions/{session_id}/presets/not-real/thumbnail")

    assert auto.status_code == 200
    assert filtered.status_code == 200
    assert auto.content_type == "image/jpeg"
    assert filtered.data.startswith(b"\xff\xd8")
    assert filtered.data != auto.data
    assert filtered.headers["Cache-Control"] == "private, no-store"
    assert unknown.status_code == 404


def test_superseded_result_url_expires_after_filter_change():
    client = app.test_client()
    upload = client.post(
        "/upload",
        data={"photo": (io.BytesIO(_jpeg_bytes()), "photo.jpg")},
        content_type="multipart/form-data",
    ).get_json()
    old_result_url = upload["after"]

    applied = client.post(
        "/apply",
        json={"session_id": upload["session_id"], "preset": "warm_film", "revision": 1},
    ).get_json()

    assert client.get(old_result_url).status_code == 404
    assert client.get(applied["after"]).status_code == 200


def test_session_state_restores_current_filter_and_intensity():
    client = app.test_client()
    upload = client.post(
        "/upload",
        data={"photo": (io.BytesIO(_jpeg_bytes()), "photo.jpg")},
        content_type="multipart/form-data",
    ).get_json()
    session_id = upload["session_id"]
    applied = client.post(
        "/apply",
        json={
            "session_id": session_id,
            "preset": "warm_film",
            "intensity": 35,
            "revision": 4,
        },
    )

    restored = client.get(f"/sessions/{session_id}")

    assert applied.status_code == 200
    assert restored.status_code == 200
    body = restored.get_json()
    assert body["preset"] == "warm_film"
    assert body["intensity"] == 35
    assert body["revision"] == 4
    assert body["after"] == applied.get_json()["after"]


def test_older_filter_revision_cannot_replace_newer_result():
    client = app.test_client()
    upload = client.post(
        "/upload",
        data={"photo": (io.BytesIO(_jpeg_bytes()), "photo.jpg")},
        content_type="multipart/form-data",
    ).get_json()
    session_id = upload["session_id"]

    newer = client.post(
        "/apply",
        json={"session_id": session_id, "preset": "warm_film", "intensity": 80, "revision": 5},
    )
    older = client.post(
        "/apply",
        json={"session_id": session_id, "preset": "cool_moody", "intensity": 20, "revision": 4},
    )

    assert newer.status_code == 200
    assert older.status_code == 409
    assert older.get_json()["stale"] is True
    assert client.get(f"/sessions/{session_id}").get_json()["preset"] == "warm_film"


def test_missing_session_state_and_image_return_404():
    client = app.test_client()

    assert client.get("/sessions/not-real").status_code == 404
    assert client.get("/sessions/not-real/images/result").status_code == 404
