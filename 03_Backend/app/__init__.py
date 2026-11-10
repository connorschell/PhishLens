"""PhishLens API package.

The version lives here and nowhere else. It was previously written out in both
main.py and the /health handler, which drifted: /health kept reporting 0.2.0
after WBS 3.4 shipped as 0.3.0, so the one endpoint whose job is to say what is
running was the one endpoint lying about it.
"""

__version__ = "0.3.0"
