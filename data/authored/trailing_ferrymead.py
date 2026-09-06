"""Ferrymead's ledger before the window — 2026-03-20 to 2026-06-08.

Thirty-four transactions, clearing the 30-row floor Drift needs to split a
baseline from a comparison window. They predate the submitted runs and so
legitimately carry no run_ref.

The declines cluster once, benignly, on an expired card. That has to exist:
the rule that reads decline clusters as pro-testing is a judgement, and a
judgement with no benign example to weigh against is just a keyword.
"""
# (date, merchant, amount, status)
T = [
 ("03-20","NOR",118.00,"settled"),("03-23","HRT",119.00,"settled"),("03-24","VLT",279.00,"settled"),
 ("03-25","ATE",148.00,"settled"),("03-26","TRK",187.00,"settled"),("03-30","SLV",165.00,"settled"),
 ("03-31","PTC",112.00,"settled"),("04-01","CYC",128.00,"settled"),("04-02","NOR",150.00,"settled"),
 ("04-06","DSK",250.00,"settled"),("04-07","TRK",214.00,"settled"),
 # a benign cluster: the shopper's card had expired
 ("04-08","AUR",279.00,"declined"),("04-08","AUR",279.00,"declined"),("04-09","AUR",279.00,"settled"),
 ("04-13","MKT",238.00,"settled"),("04-14","STL",200.00,"settled"),("04-15","GRV", 21.50,"settled"),
 ("04-20","KDO", 22.00,"settled"),("04-21","VLT",250.00,"settled"),("04-22","SLV",340.00,"settled"),
 ("04-27","DSK",385.00,"settled"),("04-28","TRK",329.00,"settled"),("05-04","PGE", 34.00,"settled"),
 ("05-05","BRW", 38.00,"settled"),
 # a return: the shopper sent it back
 ("05-06","ATE",445.00,"reversed"),
 ("05-11","VLT",429.00,"settled"),("05-12","DSK", 42.00,"settled"),("05-13","STL",400.00,"settled"),
 ("05-18","AUR",549.00,"settled"),("05-19","KDO", 54.00,"settled"),("05-20","STL",500.00,"settled"),
 ("05-26","TRK", 74.50,"settled"),("06-01","PGE", 78.00,"settled"),("06-08","BRW", 89.00,"settled"),
]
