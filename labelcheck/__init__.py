"""Alcohol label compliance checking.

A local, on-device toolkit for comparing alcohol beverage label artwork
against declared product data and the federal labelling rules in 27 CFR.

No part of this package contacts a cloud service. The only module capable of
opening a network connection is `application.fetch_from_ttb`, which is
disabled by default.
"""

__version__ = "1.0.0"
