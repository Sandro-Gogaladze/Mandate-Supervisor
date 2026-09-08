"""Wrenfield's ledger before the window — 2026-04-07 to 2026-06-26.

Thirty-two transactions, clearing the 30-row floor Drift needs to split a
baseline from a comparison window. They predate the submitted runs and carry
no run_ref.
"""
# (date, merchant, amount, status)
T = [
 ("04-07","NOR",118.00,"settled"),("04-08","PGE", 34.00,"settled"),("04-09","HRT",119.00,"settled"),
 ("04-13","LUM", 48.00,"settled"),("04-14","VLT",279.00,"settled"),("04-15","TRK",187.00,"settled"),
 ("04-20","CYC",128.00,"settled"),("04-21","ATE",148.00,"settled"),("04-22","DSK",250.00,"settled"),
 ("04-27","GRV", 68.00,"settled"),
 # a benign cluster: the shopper's card had expired
 ("04-28","AUR",398.00,"declined"),("04-28","AUR",398.00,"declined"),("04-29","AUR",398.00,"settled"),
 ("05-04","KDO", 96.00,"settled"),("05-05","PTC",112.00,"settled"),("05-06","STL",420.00,"settled"),
 ("05-11","NOR",436.00,"settled"),("05-12","BRW", 38.00,"settled"),("05-13","SLV",165.00,"settled"),
 ("05-18","VLT",478.00,"settled"),("05-19","PGE", 18.50,"settled"),("05-20","TRK",214.00,"settled"),
 ("05-26","LUM", 29.50,"settled"),("06-01","HRT",512.00,"settled"),
 # a return: the shopper sent it back
 ("06-02","ATE",445.00,"reversed"),
 ("06-08","DSK", 68.00,"settled"),("06-09","GRV", 21.50,"settled"),("06-10","CYC", 96.00,"settled"),
 ("06-15","NOR",150.00,"settled"),("06-16","KDO", 22.00,"settled"),("06-22","VLT",200.00,"settled"),
 ("06-26","AUR",550.00,"settled"),
]
