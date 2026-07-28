# Swiss Ephemeris data (required by PyJHora / pyswisseph)

PyJHora wheels no longer ship `.se1` files. These cover modern birth dates
(~1800–2400). `engine.py` calls `swe.set_ephe_path()` to this folder on import.
