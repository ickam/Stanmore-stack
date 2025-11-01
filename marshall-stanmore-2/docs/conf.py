import sys
import pathlib


sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

project = "marshallstanmore2"
copyright = "2025, rabbit-aaron"
author = "rabbit-aaron"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx_autodoc_typehints",
]

exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

autodoc_default_options = {
    "members": True,
    "undoc-members": True,
    "show-inheritance": True,
}

html_theme = "alabaster"
