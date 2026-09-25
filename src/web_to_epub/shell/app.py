"""Flask app factory: thin HTTP routes over shell.convert.convert."""

import json
import re

from flask import Flask, Response, jsonify, request

from web_to_epub.core.epub_builder import ImageData
from web_to_epub.core.url_list import clean_url_list
from web_to_epub.shell.convert import ConvertError, Options, convert
from web_to_epub.shell.fetch_pages import PageChapter, fetch_pages

_DEFAULT_MAX_CONTENT_LENGTH = 60 * 1024 * 1024


def _slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "book"


def _error(message: str, status: int = 400):
    return jsonify(error=message), status


def create_app(config: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = _DEFAULT_MAX_CONTENT_LENGTH
    if config:
        app.config.update(config)

    @app.get("/")
    def index():
        return app.send_static_file("index.html")

    @app.post("/convert")
    def convert_route():
        form = request.form
        uploads = request.files.getlist("files")
        if any(not f.filename for f in uploads):
            return _error("Every uploaded file needs a name")
        files = [(f.filename, f.read()) for f in uploads]

        order = None
        if form.get("order"):
            try:
                order = json.loads(form["order"])
            except json.JSONDecodeError:
                return _error("order must be a JSON list of filenames")
            if not isinstance(order, list) or not all(isinstance(n, str) for n in order):
                return _error("order must be a JSON list of filenames")

        cover = None
        cover_file = request.files.get("cover")
        if cover_file is not None and cover_file.filename:
            cover = ImageData(cover_file.read(), cover_file.mimetype)

        options = Options(
            title=form.get("title", ""),
            author=form.get("author", ""),
            language=form.get("language") or "en",
            description=form.get("description", ""),
            strip_suffix=form.get("strip_suffix") or None,
            order=order,
            cover=cover,
            allow_loopback_for_tests=app.config.get("ALLOW_LOOPBACK_FOR_TESTS", False),
        )
        result = convert(files, options)
        if isinstance(result, ConvertError):
            return _error(result.message, 413 if result.code == "too_large" else 400)

        return Response(
            result.epub_bytes,
            mimetype="application/epub+zip",
            headers={
                "Content-Disposition": f'attachment; filename="{_slug(options.title)}.epub"',
                "X-Warnings": str(len(result.warnings)),
            },
        )

    @app.post("/fetch")
    def fetch_route():
        body = request.get_json(silent=True)
        urls = body.get("urls") if isinstance(body, dict) else None
        if not isinstance(urls, list) or not urls or not all(isinstance(u, str) for u in urls):
            return _error("urls must be a non-empty list of strings")
        try:
            cleaned = clean_url_list(urls)
        except ValueError as exc:
            return _error(str(exc))
        if not cleaned.urls and not cleaned.errors:
            return _error("urls must be a non-empty list of strings")
        if cleaned.errors:
            return _error("; ".join(f"{e.entry}: {e.reason}" for e in cleaned.errors))

        results = fetch_pages(
            cleaned.urls,
            allow_loopback_for_tests=app.config.get("ALLOW_LOOPBACK_FOR_TESTS", False),
        )
        chapters = [
            {"filename": r.filename, "url": r.url, "title": r.title, "markdown": r.markdown}
            for r in results
            if isinstance(r, PageChapter)
        ]
        errors = [
            {"url": r.url, "message": r.message}
            for r in results
            if not isinstance(r, PageChapter)
        ]
        return jsonify(chapters=chapters, errors=errors)

    return app
