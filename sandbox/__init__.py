"""The policy sandbox: version a rulebook, run it over the labelled corpus,
see what changed before any of it becomes policy.

Deliberately its own package, not part of `registry/`. The registry is what
is in force; this is where candidates live and are measured. Keeping them
apart is what stops a draft ever being loaded by a live review.
"""
