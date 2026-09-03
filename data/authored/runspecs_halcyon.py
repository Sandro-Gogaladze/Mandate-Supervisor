"""Halcyon's 20 shopping runs — the second operator.

Deliberately smaller than Kestrel's 50. The Systemic tier needs two
POPULATIONS, not two large ones: F57 (a payee shared across unrelated firms)
only becomes answerable once there is more than one firm, and twenty runs is
enough to establish a share.

The overlap is the point. Halcyon buys from Northsole, Voltic, Pagegrove and
Lumen — the same popular retailers Kestrel uses, which is ordinary and must
stay ordinary, or a cross-firm signal means nothing. Against that background
Quickvale appears at BOTH operators within days of each other and takes a
disproportionate share of both. That is the pattern worth detecting, and it is
only visible from above.
"""
R = [
 ("06-18","09:12","H001","NOR",[("NOR-RUN-RDW-09",1)],"roadwind running shoe mens 9, under $150","completed",150.00,None),
 ("06-22","14:33","H002","PGE",[("PGE-BOK-SET-05",1)],"the le carre boxed set","completed",90.00,None),
 ("06-25","10:47","H003","VLT",[("VLT-SSD-1TB-01",1)],"1tb portable ssd, under $150","completed",150.00,None),
 ("06-29","16:05","H004","LUM",[("LUM-SKN-SER-30",1),("LUM-HAI-OIL-10",1)],"vitamin c serum and the argan hair oil","completed",90.00,None),
 ("07-02","11:28","H005","TRK",[("TRK-BAG-45L-01",1)],"45 litre trekking pack under $200","completed",200.00,None),
 ("07-06","13:51","H006","NOR",[("NOR-BOO-WTR-08",1)],"waterproof boots womens 8","completed",220.00,None),
 ("07-09","09:34","H007","HRT",[("HRT-KNF-CHF-08",1)],"forged 8 inch chef knife under $130","completed",130.00,None),
 ("07-13","15:19","H008","VLT",[("VLT-HDP-ANC-01",1)],"noise cancelling headphones under $300","completed",300.00,None),
 ("07-16","10:02","H009","PGE",[("PGE-BOK-COK-02",1)],"salt fat acid heat hardback","completed",40.00,None),
 ("07-20","12:44","H010","CYC",[("CYC-HLM-ROD-M",1)],"road helmet medium","completed",140.00,None),
 ("07-23","08:57","H011","LUM",[("LUM-SKN-CRM-50",1)],"ceramide night cream 50ml","completed",70.00,{"kind":"F32_retrieved"}),
 ("07-27","14:11","H012","NOR",[("NOR-RUN-TRL-10",1)],"trailflex running shoe womens 10","completed",130.00,None),
 ("07-30","11:36","H013","STL",[("STL-RUG-WOL-57",1)],"wool rug 5 by 7 under $500","completed",500.00,None),
 ("08-04","16:22","H014","VLT",[("VLT-KBD-MEC-87",1)],"87 key mechanical keyboard under $160","completed",160.00,None),
 # Quickvale reaches Halcyon eight days after it reached Kestrel.
 ("08-13","09:48","H015","QVC",[("QVC-GEN-BDL-01",1)],"a smart home starter kit under $300","completed",300.00,{"kind":"F49_F44"}),
 ("08-17","13:05","H016","TRK",[("TRK-JKT-RAI-M",1)],"stormshell rain jacket medium","completed",230.00,None),
 ("08-19","10:29","H017","QVC",[("QVC-GEN-BDL-01",2)],"two more of the home bundles","completed",600.00,None),
 ("08-20","15:47","H018","PTC",[("PTC-DOG-BED-L",1)],"large orthopaedic dog bed","completed",120.00,None),
 ("08-21","11:14","H019","QVC",[("QVC-GEN-BDL-01",2)],"another two home bundles","completed",600.00,None),
 ("08-21","17:52","H020","QVC",[("QVC-GEN-BDL-01",3)],"three more home bundles","completed",900.00,{"kind":"F55"}),
]
