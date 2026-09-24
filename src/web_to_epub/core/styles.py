"""Default EPUB stylesheet."""

STYLESHEET = """\
body {
    font-family: "Iowan Old Style", "Palatino Linotype", "URW Palladio L", P052, serif;
    line-height: 1.6;
    text-align: justify;
    hyphens: auto;
}

h1, h2, h3 {
    font-family: "Avenir Next", "Helvetica Neue", Helvetica, Arial, sans-serif;
    font-weight: 600;
    line-height: 1.2;
    margin-top: 2em;
    margin-bottom: 1em;
    text-align: left;
    page-break-after: avoid;
}

h1 {
    font-size: 2em;
    border-bottom: 2px solid #333;
    padding-bottom: 0.3em;
}

h2 {
    font-size: 1.5em;
}

p {
    margin-top: 0;
    margin-bottom: 1em;
    text-indent: 1.5em;
    orphans: 2;
    widows: 2;
}

h1 + p, h2 + p, h3 + p {
    text-indent: 0;
}

img {
    max-width: 100%;
    height: auto;
    display: block;
    margin: 1.5em auto;
    page-break-inside: avoid;
}

figure {
    margin: 1.5em 0;
    text-align: center;
    page-break-inside: avoid;
}

figcaption {
    font-size: 0.85em;
    font-style: italic;
    color: #666;
    text-align: center;
    margin-top: 0.5em;
    margin-bottom: 1.5em;
    text-indent: 0;
}

blockquote {
    margin: 1em 2em;
    padding-left: 1em;
    border-left: 3px solid #ccc;
    font-style: italic;
}

pre, code {
    font-family: "Courier New", Courier, monospace;
    font-size: 0.9em;
    background-color: #f5f5f5;
}

pre {
    padding: 1em;
    margin: 1em 0;
}

a {
    color: #2a5db0;
    text-decoration: none;
}

hr {
    border: none;
    border-top: 1px solid #ccc;
    margin: 2em 0;
}
"""
