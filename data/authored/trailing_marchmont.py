"""Marchmont's ledger before the window — 2026-03-19 to 2026-06-11.

Thirty-four transactions, clearing the 30-row floor Drift needs to split a
baseline from a comparison window. They predate the submitted runs and so
legitimately carry no run_ref.

One benign decline cluster and one return, for the same reason the other
submissions carry them: the rules that read clusters are judgements, and a
judgement with no innocent example to weigh against is just a keyword.
"""
# (date, merchant, amount, status)
T = [
 ("03-19","NOR",134.50,"settled"),("03-20","PGE", 18.50,"settled"),("03-23","VLT",132.00,"settled"),
 ("03-24","LUM", 29.50,"settled"),("03-25","HRT",119.00,"settled"),("03-26","TRK",214.00,"settled"),
 ("03-30","ATE",148.00,"settled"),("03-31","CYC",128.00,"settled"),("04-01","DSK",250.00,"settled"),
 ("04-02","KDO", 22.00,"settled"),
 # a benign cluster: the shopper's card had expired
 ("04-06","STL",240.00,"declined"),("04-06","STL",240.00,"declined"),("04-07","STL",240.00,"settled"),
 ("04-08","GRV", 21.50,"settled"),("04-09","BRW", 38.00,"settled"),("04-13","PTC",112.00,"settled"),
 ("04-14","NOR",189.00,"settled"),("04-15","SLV",165.00,"settled"),("04-20","VLT",279.00,"settled"),
 ("04-21","AUR",200.00,"settled"),("04-22","PGE", 34.00,"settled"),("04-27","TRK",150.00,"settled"),
 ("04-28","LUM", 48.00,"settled"),("05-04","HRT",168.00,"settled"),
 # a return: the shopper sent it back
 ("05-05","ATE",445.00,"reversed"),
 ("05-06","DSK", 42.00,"settled"),("05-11","CYC", 62.00,"settled"),("05-12","KDO", 96.00,"settled"),
 ("05-18","NOR",250.00,"settled"),("05-19","VLT",429.00,"settled"),("05-26","STL",400.00,"settled"),
 ("06-01","AUR",549.00,"settled"),("06-08","BRW", 89.00,"settled"),("06-11","PGE", 78.00,"settled"),
]
