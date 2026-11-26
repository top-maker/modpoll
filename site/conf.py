"""Sphinx configuration for the modpoll, modsim and modpoll-wot documentation site (DOC-02)."""

project = "modpoll"
author = "Ying Shaodong"
copyright = "2021-2026, Ying Shaodong"

extensions = ["myst_parser", "sphinxarg.ext", "sphinx_reredirects"]
myst_enable_extensions = ["colon_fence", "deflist"]
myst_heading_anchors = 3

exclude_patterns = ["_build"]
# Command-line help keeps its literal "--option" text.
smartquotes = False

# Pages of the earlier /v2/ site, linked from published release notes.
redirects = {
    "installation": "guide/installation.html",
    "quickstart": "guide/quickstart.html",
    "usage": "guide/read-a-device.html",
    "configure": "reference/modpoll/configuration.html",
    "csv-migration": "guide/migrate-from-v1-csv.html",
    "v1-compatibility": "reference/modpoll/v1-compatibility.html",
    "changelog": "reference/modpoll/changelog.html",
}

html_theme = "furo"
html_title = "modpoll, modsim and modpoll-wot"
html_copy_source = False
html_baseurl = "https://top-maker.github.io/modpoll/v2/"
html_theme_options = {
    "source_repository": "https://github.com/top-maker/modpoll/",
    "source_branch": "v2",
    "source_directory": "site/",
    "announcement": (
        "This is the 2.x preview of modpoll, modsim and modpoll-wot. "
        'Stable modpoll 1.x (CSV configurations) is documented at <a href="/modpoll/1.x/">1.x</a>.'
    ),
}

linkcheck_ignore = [
    # Placeholders and local addresses in examples.
    r"https?://(127\.0\.0\.1|localhost)",
    # Historical modsim changelog entries compare against tags that were never created.
    r"https://github\.com/top-maker/modsim/compare/v0\.(3\.4|4\.0)\.\.\.",
]
