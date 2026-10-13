"""Chat commands that run without an AI model.

A message is matched against a catalog of known commands (catalog.py) by a small text matcher
(matcher.py); names of customers, items and other records are looked up in the database
(entities.py) and numbers, amounts and dates are read with rules (text.py). Only messages that no
command fits, or that a command marks as too complex, go to the AI model.
"""
