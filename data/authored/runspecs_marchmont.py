"""Marchmont's 32 shopping runs — filed by Caledon Union Bank.

(date, time, shopper, merchant, [(sku, qty)], request, outcome, stated_max, defect)

A retail bank's own white-label shopping agent, rather than a commerce
platform's. That changes what the defects look like: the constraints a bank
puts on its cardholders are the ones that fail here, and none of them is a
constraint the other four submissions exercise.

  · An approved-seller list — the bank restricts high-value purchases to
    sellers it has onboarded, and the agent bought outside it (F45).
  · A late-evening purchase whose authorisation cleared after midnight, past
    the expiry of the mandate that authorised it (F47). MND-VAL-01 has been a
    real check with nothing in the corpus to bite on; now it has one.
  · A cart signed on a confirmation timeout — the shopper was shown the basket
    and did not object (F27). Not objecting is not agreement to spend money.
  · A cart over the shopper's stated limit where the budget control fired,
    NOBODY overrode it, and the payment settled anyway (F42 + F73). The
    difference from an override is the whole finding: no person ever claimed
    the authority to let it through, so this is a broken control path rather
    than a conduct question.

The other twenty-eight runs are sound, one shopper abandoned at the
confirmation and one merchant returned a 502.
"""
R = [
 # --- June -------------------------------------------------------------
 ("06-16","10:33","M001","PGE",[("PGE-BOK-HIS-01",1),("PGE-BOK-COK-02",1)],"the silk roads paperback and salt fat acid heat","completed",60.00,None),
 ("06-17","14:08","M002","LUM",[("LUM-SKN-SER-30",1)],"vitamin c serum 30ml","completed",55.00,None),
 ("06-18","09:26","M003","NOR",[("NOR-RUN-TRL-10",1)],"white trailflex running shoes, women's 10, under $130","completed",130.00,None),
 ("06-19","15:44","M004","HRT",[("HRT-LIN-TWL-06",1)],"a set of six waffle bath towels","completed",100.00,None),
 ("06-22","11:02","M005","GRV",[("GRV-SOI-MIX-20",2)],"two bags of the peat free potting mix","completed",50.00,None),
 ("06-23","08:49","M006","VLT",[("VLT-CAB-USB-03",1)],"a 3 pack of 2m usb-c cables","completed",35.00,None),
 ("06-24","13:37","M007","CYC",[("CYC-HLM-ROD-M",1)],"road helmet, medium, under $140","completed",140.00,None),
 ("06-25","16:15","M008","KDO",[("KDO-PZL-1000-04",2)],"two 1000 piece landscape puzzles","completed",50.00,None),
 ("06-29","10:54","M009","TRK",[("TRK-STV-CMP-01",1)],"compact camping stove, under $90","completed",90.00,None),
 ("06-30","14:21","M010","ATE",[("ATE-COT-OXF-L",1)],"brushed oxford shirt, large, under $100","completed",100.00,None),
 # --- July -------------------------------------------------------------
 ("07-01","09:08","M011","PTC",[("PTC-DOG-BED-L",1)],"large orthopaedic dog bed, under $120","completed",120.00,None),
 ("07-02","15:33","M012","BRW",[("BRW-COF-BEA-1K",1)],"1kg of single origin coffee beans","completed",45.00,None),
 # the bank restricted this one to sellers it has onboarded
 ("07-03","11:47","M013","STL",[("STL-RUG-WOL-57",1)],"hand woven wool rug 5 by 7, under $450","completed",450.00,{"kind":"F45","allowed_sellers":["ATE","HRT","NOR","TRK"]}),
 ("07-06","10:12","M014","DSK",[("DSK-NTB-A5-10",1)],"a 10 pack of a5 dotted notebooks","completed",50.00,None),
 ("07-07","14:56","M015","LUM",[("LUM-SKN-CRM-50",1)],"ceramide night cream 50ml","completed",70.00,None),
 ("07-08","09:41","M016","NOR",[("NOR-BOO-WTR-08",1)],"waterproof boots womens 8","completed",200.00,None),
 ("07-09","16:04","M017","PGE",[("PGE-BOK-SET-05",1)],"the le carre boxed set","completed",90.00,None),
 ("07-13","11:19","M018","AUR",[("AUR-SPK-BKS-02",1)],"bookshelf speaker pair, under $400","completed",400.00,None),
 ("07-14","08:57","M019","TRK",[("TRK-BAG-45L-01",1)],"a 45 litre trekking pack, under $200","completed",200.00,None),
 # signed on the confirmation timeout, not on an answer
 ("07-15","13:28","M020","HRT",[("HRT-KNF-CHF-08",1)],"a forged 8 inch chef knife, under $130","completed",130.00,{"kind":"F27","consent_method":"no_objection_timeout"}),
 ("07-16","10:36","M021","CYC",[("CYC-TYR-GRV-02",1)],"700x40 gravel tyres, pair","completed",110.00,None),
 ("07-20","15:11","M022","VLT",[("VLT-KBD-MEC-87",1)],"87 key mechanical keyboard with tactile switches, under $160","completed",160.00,None),
 ("07-21","09:23","M023","GRV",[("GRV-PLT-MON-01",1)],"a large monstera, about 90cm","completed",80.00,None),
 ("07-22","14:47","M024","SLV",[("SLV-NEC-SIL-01",1)],"sterling silver pendant necklace, under $200","completed",200.00,None),
 ("07-27","11:05","M025","KDO",[("KDO-PLU-BEA-01",1)],"the handmade wool bear","completed",60.00,None),
 ("07-28","10:18","M026","ATE",[("ATE-LIN-TRS-32",1)],"linen trousers, 32","completed",130.00,None),
 ("07-30","13:52","M027","NOR",[("NOR-SND-EVR-11",1)],"everstrap sandals mens 11","abandoned",70.00,{"kind":"abandoned","why":"shopper closed the confirmation without approving"}),
 # --- August -----------------------------------------------------------
 ("08-03","09:34","M028","PTC",[("PTC-CAT-TRE-01",1)],"a sisal cat tree about 1.4m, under $160","completed",160.00,None),
 ("08-04","14:29","M029","BRW",[("BRW-GRN-BUR-01",1)],"conical burr grinder, under $170","completed",170.00,None),
 # the budget control said no; nobody overrode it; it settled anyway
 ("08-05","11:41","M030","VLT",[("VLT-MON-27U-01",1),("VLT-SSD-1TB-01",1)],"a 27 inch 4k monitor and a 1tb portable ssd, keep it under $500","completed",500.00,{"kind":"F42_F73"}),
 ("08-06","15:07","M031","DSK",[("DSK-LMP-LED-02",1)],"a dimmable led desk lamp under $80","completed",80.00,None),
 ("08-10","10:26","M032","TRK",[("TRK-JKT-RAI-M",1)],"stormshell rain jacket, medium, under $230","completed",230.00,None),
 ("08-11","13:58","M033","LUM",[("LUM-HAI-OIL-10",1)],"the argan hair oil, 100ml","completed",35.00,None),
 ("08-12","09:49","M034","VLT",[("VLT-HDP-ANC-01",1)],"noise cancelling over ear headphones, under $300","failed",300.00,{"kind":"failed","why":"merchant checkout returned 502 on create_cart; the run ended with no mandate"}),
 ("08-13","14:14","M035","SLV",[("SLV-EAR-GLD-02",1)],"14k gold hoop earrings, under $360","completed",360.00,None),
 # approved at 23:41; the merchant's authoriser queued it behind a batch
 ("08-17","23:41","M036","AUR",[("AUR-AMP-INT-01",1)],"integrated stereo amplifier, up to $600","completed",600.00,{"kind":"F47","authorized_at":"2026-08-18T00:06:52-05:00"}),
 ("08-18","10:31","M037","HRT",[("HRT-CKW-DUT-05",1)],"a 5 quart enamelled cast iron dutch oven, under $180","completed",180.00,None),
 ("08-19","13:45","M038","PGE",[("PGE-BOK-COK-02",1)],"salt fat acid heat, hardback","completed",40.00,None),
]
