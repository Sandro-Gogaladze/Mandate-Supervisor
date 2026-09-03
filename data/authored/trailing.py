"""The agent's ledger before the submitted window — 2026-03-18 to 2026-06-12.

Authored. It exists because DRIFT-* needs 30+ transactions for a
baseline/comparison split; without it a third of the rulebook returns `absent`
on every run. These predate the runs, so they legitimately carry no run_ref —
which is what makes an *in-window* transaction without one a finding.

Status mix is deliberate. The realism target is 94-98% settled, 2-5% declined,
0.5-1% reversed, and declines must CLUSTER — an expired card fails three times
in an afternoon, not three times a quarter. F58 keys on the pattern, so benign
clusters have to exist or every cluster looks malicious.
"""
# (date, merchant, amount, status)
T = [
 ("03-18","NOR",150.00,"settled"),("03-19","PGE", 52.50,"settled"),("03-20","VLT",279.00,"settled"),
 ("03-23","LUM", 48.00,"settled"),("03-24","TRK",187.00,"settled"),("03-25","ATE",148.00,"settled"),
 ("03-26","HRT",119.00,"settled"),("03-30","CYC", 62.00,"settled"),("03-31","DSK",385.00,"settled"),
 ("04-01","KDO", 96.00,"settled"),("04-02","NOR",189.00,"settled"),("04-06","BRW", 38.00,"settled"),
 ("04-07","VLT",429.00,"settled"),("04-08","PTC",112.00,"settled"),("04-09","GRV", 68.00,"settled"),
 # a benign cluster: one shopper's card had expired
 ("04-13","AUR",398.00,"declined"),("04-13","AUR",398.00,"declined"),("04-13","AUR",398.00,"declined"),
 ("04-14","AUR",398.00,"settled"),
 ("04-15","STL",400.00,"settled"),("04-16","PGE", 18.50,"settled"),("04-20","SLV",165.00,"settled"),
 ("04-21","ATE", 92.00,"settled"),("04-22","TRK",214.00,"settled"),("04-23","LUM", 64.00,"settled"),
 ("04-27","HRT",168.00,"settled"),("04-28","VLT",132.00,"settled"),("04-29","NOR", 62.00,"settled"),
 ("04-30","DSK", 75.00,"settled"),("05-04","CYC",128.00,"settled"),("05-05","KDO", 22.00,"settled"),
 ("05-06","BRW",200.00,"settled"),("05-07","GRV", 21.50,"settled"),("05-11","AUR",549.00,"settled"),
 ("05-12","PGE", 78.00,"settled"),("05-13","MKT",141.00,"settled"),("05-14","STL",615.00,"settled"),
 # a return: the shopper sent it back
 ("05-18","ATE",445.00,"reversed"),
 ("05-19","LUM", 29.50,"settled"),("05-20","TRK", 74.50,"settled"),("05-21","NOR",250.00,"settled"),
 ("05-26","VLT",150.00,"settled"),("05-27","HRT", 88.00,"settled"),("05-28","SLV",340.00,"settled"),
 ("05-29","PTC",148.00,"settled"),("06-01","CYC", 96.00,"settled"),("06-02","DSK", 42.00,"settled"),
 ("06-03","KDO", 54.00,"settled"),("06-04","GRV",100.00,"settled"),("06-08","BRW", 50.00,"settled"),
 ("06-09","PGE", 34.00,"settled"),("06-10","VLT", 24.00,"settled"),("06-11","ATE",118.00,"settled"),
 ("06-12","NOR",118.00,"settled"),
 ("06-12","MKT",238.00,"declined"),
]
