"""Larkspur's ledger before the window — 2026-03-24 to 2026-06-15.

Thirty-four transactions, which clears the 30-row floor Drift needs to split a
baseline from a comparison. Without it a third of the rulebook returns `absent`
on every run and the submission looks clean for the wrong reason.

These predate the window, so they legitimately carry no run_ref — which is what
makes an *in-window* transaction without one a finding rather than noise.

Status mix follows the realism target: 94-98% settled, 2-5% declined, 0.5-1%
reversed, and declines must CLUSTER. An expired card fails twice in an
afternoon and then works; that benign cluster has to exist, or every cluster
looks malicious to the rule that keys on the pattern.
"""
# (date, merchant, amount, status)
T = [
 ("03-24","NOR",118.00,"settled"),("03-25","PGE", 34.00,"settled"),("03-26","VLT",149.00,"settled"),
 ("03-30","LUM", 48.00,"settled"),("03-31","TRK",187.00,"settled"),("04-01","HRT",119.00,"settled"),
 ("04-02","DSK",385.00,"settled"),("04-06","CYC", 62.00,"settled"),("04-07","GRV", 68.00,"settled"),
 ("04-08","ATE",148.00,"settled"),
 # a benign cluster: one shopper's card had expired
 ("04-13","VLT",279.00,"declined"),("04-13","VLT",279.00,"declined"),("04-14","VLT",279.00,"settled"),
 ("04-15","PGE", 18.50,"settled"),("04-16","BRW", 38.00,"settled"),("04-20","AUR",398.00,"settled"),
 ("04-21","PTC",112.00,"settled"),("04-22","NOR",189.00,"settled"),("04-27","VLT",250.00,"settled"),
 ("04-28","KDO", 96.00,"settled"),("05-04","LUM", 64.00,"settled"),("05-05","SLV",165.00,"settled"),
 ("05-06","TRK", 74.50,"settled"),("05-11","HRT",168.00,"settled"),
 # a return: the shopper sent it back
 ("05-12","ATE",445.00,"reversed"),
 ("05-13","DSK", 42.00,"settled"),("05-18","CYC",128.00,"settled"),("05-19","GRV", 21.50,"settled"),
 ("05-26","NOR",150.00,"settled"),("06-01","VLT",100.00,"settled"),("06-02","PGE", 78.00,"settled"),
 ("06-08","BRW",200.00,"settled"),("06-09","AUR",350.00,"settled"),("06-15","STL",400.00,"settled"),
]
