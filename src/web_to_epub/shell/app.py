"""Flask app factory: thin HTTP routes over shell.convert.convert."""

import json
import re

from flask import Flask, Response, jsonify, request

from web_to_epub.core.epub_builder import ImageData
from web_to_epub.shell.convert import ConvertError, Options, convert

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
        files = [(f.filename, f.read()) for f in request.files.getlist("files")]

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

    return app
