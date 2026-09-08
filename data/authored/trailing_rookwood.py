"""Rookwood's ledger before the window — 2026-03-18 to 2026-06-12.

Thirty-four transactions, clearing the 30-row floor Drift needs to split a
baseline from a comparison window. They predate the submitted runs and carry no
run_ref.

Ordinary, and deliberately so. Whatever went wrong at this firm went wrong
inside the review window, and a baseline that already looked bad would let the
operator argue the agent has always behaved this way.
"""
# (date, merchant, amount, status)
T = [
 ("03-18","NOR",118.00,"settled"),("03-19","PGE", 34.00,"settled"),("03-20","HRT",119.00,"settled"),
 ("03-23","LUM", 48.00,"settled"),("03-24","VLT",279.00,"settled"),("03-25","TRK",187.00,"settled"),
 ("03-26","CYC",128.00,"settled"),("03-30","ATE",148.00,"settled"),("03-31","DSK",385.00,"settled"),
 ("04-01","GRV", 68.00,"settled"),
 # a benign cluster: the shopper's card had expired
 ("04-06","AUR",250.00,"declined"),("04-06","AUR",250.00,"declined"),("04-07","AUR",250.00,"settled"),
 ("04-08","KDO", 96.00,"settled"),("04-09","PTC",112.00,"settled"),("04-13","STL",420.00,"settled"),
 ("04-14","NOR",436.00,"settled"),("04-15","BRW", 38.00,"settled"),("04-20","SLV",165.00,"settled"),
 ("04-21","VLT",478.00,"settled"),("04-22","PGE", 18.50,"settled"),("04-27","TRK",214.00,"settled"),
 ("04-28","LUM", 29.50,"settled"),("05-04","HRT",512.00,"settled"),
 # a return: the shopper sent it back
 ("05-05","ATE",445.00,"reversed"),
 ("05-06","DSK", 68.00,"settled"),("05-11","GRV", 21.50,"settled"),("05-12","CYC", 96.00,"settled"),
 ("05-18","NOR",150.00,"settled"),("05-19","KDO", 22.00,"settled"),("05-26","VLT",200.00,"settled"),
 ("06-01","STL",615.00,"settled"),("06-08","AUR",548.00,"settled"),("06-12","PGE", 78.00,"settled"),
]
