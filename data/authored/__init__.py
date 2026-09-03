"""The authored content behind the Brightline dossier.

Every fact a supervisor could act on — which supplier, which SKUs, what
quantity, what the buyer was asked, when it happened, what went wrong — is
written here by hand. scripts/build_brightline_dossier.py only expands it into
the JSON envelope and computes totals from line items.

These files are the source of truth for the corpus. They live in the repo, not
in a scratch directory, because a corpus that cannot be regenerated is a corpus
nobody can safely change.
"""
