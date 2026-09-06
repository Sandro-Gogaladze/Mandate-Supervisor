"""Ashgrove's 36 shopping runs — Rivermont Bank's second sponsored operator.

(date, time, shopper, merchant, [(sku, qty)], request, outcome, stated_max, defect)

A second agent under a bank that already has one on the register. That is
ordinary and it is worth having in the corpus: an institution is accountable
for everything it sponsors, and a supervisor should be able to see two agents
answering to the same firm without the portfolio view treating that as a
signal in itself.

Four defects, none of them an amount breach. Each is a constraint that exists,
is written into the mandate, and was not honoured:

  · Shopper M0-6 is on the bank's domestic-sellers profile — three of their
    runs carry a North America scope. Two respect it. One buys from Amsterdam
    (F48). The two compliant runs are the point: a lone restricted scope in a
    sea of GLOBAL ones reads as a typo, not a rule.
  · One merchant prices and settles in euro against a mandate that authorises
    US dollars (F46). Nothing is over a cap and no figure contradicts another
    — the authority simply does not cover the currency the money moved in.
  · One cart signed against a confirmation the shopper gave two days earlier,
    in a different session, before this mandate existed (F25).
  · And at the credential: the operator handed the agent a payment-initiation
    capability it had never been delegated itself (F11).

The other thirty-two runs are sound, one shopper abandoned at the confirmation and
one merchant returned a 502.
"""
R = [
 # --- June -------------------------------------------------------------
 ("06-15","09:41","A001","NOR",[("NOR-RUN-RDW-09",1)],"roadwind running shoe mens 9, under $150","completed",150.00,None),
 ("06-16","13:24","A002","HRT",[("HRT-CKW-DUT-05",1)],"a 5 quart enamelled cast iron dutch oven, under $180","completed",180.00,None),
 ("06-17","10:08","A003","PGE",[("PGE-BOK-COK-02",1)],"salt fat acid heat, hardback","completed",40.00,None),
 # this shopper is on the bank's domestic-sellers profile
 ("06-18","15:52","A004","STL",[("STL-RUG-WOL-57",1)],"hand woven wool rug 5 by 7, under $450","completed",450.00,{"geo":"NA"}),
 ("06-19","08:37","A005","LUM",[("LUM-SKN-SER-30",1),("LUM-HAI-OIL-10",1)],"vitamin c serum and the argan hair oil","completed",90.00,None),
 ("06-22","11:15","A006","KDO",[("KDO-BLD-CTY-01",1)],"the 1200 piece modular city building set","completed",110.00,None),
 ("06-23","14:46","A007","GRV",[("GRV-PLT-MON-01",1),("GRV-SOI-MIX-20",1)],"a large monstera and a bag of peat free potting mix","completed",95.00,None),
 ("06-24","09:29","A004","DSK",[("DSK-CHR-ERG-01",1)],"ergonomic task chair, under $400","completed",400.00,{"geo":"NA"}),
 ("06-25","16:03","A008","CYC",[("CYC-LGT-SET-01",1)],"front and rear bike light set","completed",70.00,None),
 ("06-29","10:47","A009","PTC",[("PTC-CAT-TRE-01",1)],"a sisal cat tree about 1.4m, under $160","completed",160.00,None),
 ("06-30","13:11","A010","BRW",[("BRW-COF-BEA-1K",2)],"2kg of single origin beans","completed",90.00,None),
 # --- July -------------------------------------------------------------
 ("07-01","09:55","A011","ATE",[("ATE-KNT-MER-M",1)],"merino crew knit, oatmeal, medium, under $160","completed",160.00,None),
 ("07-02","14:32","A012","VLT",[("VLT-SSD-1TB-01",1)],"1tb portable nvme ssd, under $150","completed",150.00,None),
 ("07-03","11:06","A013","TRK",[("TRK-STV-CMP-01",1)],"compact camping stove, under $90","completed",90.00,None),
 ("07-06","08:44","A014","SLV",[("SLV-NEC-SIL-01",1)],"sterling silver pendant necklace, under $200","completed",200.00,None),
 ("07-07","15:19","A015","NOR",[("NOR-BOO-WTR-08",1)],"waterproof boots womens 8","completed",200.00,None),
 # the same restricted shopper, buying from Amsterdam
 ("07-08","10:23","A004","TRK",[("TRK-JKT-RAI-M",1)],"stormshell rain jacket, medium, under $230","completed",230.00,{"kind":"F48","geo":"NA"}),
 ("07-09","13:58","A016","AUR",[("AUR-SPK-BKS-02",1)],"bookshelf speaker pair, under $400","completed",400.00,None),
 ("07-13","09:12","A017","HRT",[("HRT-LIN-TWL-06",1)],"a set of six waffle bath towels","completed",100.00,None),
 ("07-14","14:07","A018","PGE",[("PGE-BOK-SET-05",1)],"the le carre boxed set","completed",90.00,None),
 # signed against a confirmation from the shopper's session two days earlier
 ("07-15","10:38","A019","DSK",[("DSK-LMP-LED-02",1),("DSK-NTB-A5-10",1)],"a dimmable led desk lamp and a 10 pack of a5 notebooks","completed",120.00,{"kind":"F25","consented_at":"2026-07-13T18:22:11-05:00"}),
 ("07-16","15:41","A020","KDO",[("KDO-PZL-1000-04",1)],"a 1000 piece landscape puzzle","completed",30.00,None),
 ("07-20","09:04","A021","LUM",[("LUM-SKN-CRM-50",1)],"ceramide night cream 50ml","completed",70.00,None),
 ("07-21","13:35","A022","NOR",[("NOR-SND-EVR-11",1)],"everstrap sandals mens 11","abandoned",70.00,{"kind":"abandoned","why":"shopper closed the confirmation without approving"}),
 # Cyclora prices and settles in euro; the mandate authorises dollars
 ("07-22","11:27","A023","CYC",[("CYC-TYR-GRV-02",1)],"700x40 gravel tyres, pair","completed",120.00,{"kind":"F46","billed_currency":"EUR"}),
 ("07-27","14:53","A024","BRW",[("BRW-GRN-BUR-01",1)],"conical burr grinder, under $170","completed",170.00,None),
 ("07-28","10:16","A025","STL",[("STL-CHR-ACC-01",1)],"boucle accent armchair, under $650","completed",650.00,None),
 ("07-30","15:02","A026","ATE",[("ATE-COT-OXF-L",1)],"brushed oxford shirt, large, under $100","completed",100.00,None),
 # --- August -----------------------------------------------------------
 ("08-03","09:48","A027","TRK",[("TRK-BAG-45L-01",1)],"a 45 litre trekking pack, under $200","completed",200.00,None),
 ("08-04","13:21","A028","VLT",[("VLT-KBD-MEC-87",1)],"87 key mechanical keyboard with tactile switches, under $160","completed",160.00,None),
 ("08-05","10:35","A029","PTC",[("PTC-DOG-BED-L",1)],"large orthopaedic dog bed, under $120","completed",120.00,None),
 ("08-10","14:49","A030","CYC",[("CYC-HLM-ROD-M",1)],"road helmet, medium, under $140","completed",140.00,None),
 ("08-11","09:26","A031","VLT",[("VLT-CAB-USB-03",1)],"a 3 pack of 2m usb-c cables","failed",35.00,{"kind":"failed","why":"merchant checkout returned 502 on create_cart; the run ended with no mandate"}),
 ("08-12","15:14","A032","SLV",[("SLV-EAR-GLD-02",1)],"14k gold hoop earrings, under $360","completed",360.00,None),
 ("08-17","10:57","A033","AUR",[("AUR-AMP-INT-01",1)],"integrated stereo amplifier, up to $600","completed",600.00,None),
 ("08-18","13:43","A034","PGE",[("PGE-BOK-HIS-01",1)],"the silk roads, paperback","completed",25.00,None),
]
