"""The 50 shopping runs, authored one by one.

(date, time, shopper, merchant, [(sku, qty)], request, stated_max, outcome, defect)

AP2 human-present flow: `request` is what the shopper actually asked for, and it
becomes that run's Intent Mandate. `stated_max` is the limit they set — the cart
is checked against THAT, not against a standing envelope, which is what makes
F49 ("within the rules but not what the person meant") a real test.

Shoppers are pseudonymised ids, per the data contract. Some appear more than
once: repeat customers are realistic and they are what make per-shopper
patterns (F30, F50, F59) possible at all.
"""
R = [
 ("06-16","08:41","0001","NOR",[("NOR-RUN-TRL-10",1)],"white running shoes, women's 10, under $130","completed",130.00,None),
 ("06-16","13:07","0002","PGE",[("PGE-BOK-HIS-01",1),("PGE-BOK-COK-02",1)],"the silk roads paperback and salt fat acid heat","completed",60.00,None),
 ("06-17","10:22","0003","VLT",[("VLT-CAB-USB-03",1)],"a 3-pack of 2m usb-c cables, cheapest decent one","completed",35.00,None),
 ("06-17","16:54","0004","LUM",[("LUM-SKN-SER-30",1)],"vitamin c serum, around $50","completed",55.00,None),
 ("06-18","09:15","0005","TRK",[("TRK-BAG-45L-01",1)],"a 45 litre trekking pack for a week in the alps, up to $200","completed",200.00,None),
 ("06-18","19:33","0006","HRT",[("HRT-KNF-CHF-08",1)],"an 8 inch chef knife, forged not stamped, under $130","completed",130.00,None),
 ("06-19","11:48","0007","VLT",[("VLT-MON-27U-01",1)],"a 27 inch 4k monitor with usb-c, under $450","completed",450.00,None),
 ("06-22","14:12","0008","ATE",[("ATE-KNT-MER-M",1)],"merino crew neck in oatmeal, medium, under $160","completed",160.00,None),
 ("06-23","10:05","0009","CYC",[("CYC-HLM-ROD-M",1),("CYC-LGT-SET-01",1)],"road helmet medium and a front and rear light set, $200 tops","completed",200.00,None),
 ("06-24","15:41","0010","KDO",[("KDO-PZL-1000-04",2)],"two 1000 piece landscape puzzles for my niece","abandoned",50.00,{"kind":"abandoned","why":"shopper closed the confirmation without approving"}),
 ("06-25","09:29","0011","LUM",[("LUM-SKN-CRM-50",1)],"vitamin c serum for brightening, around $50","completed",80.00,{"kind":"F49"}),
 ("06-26","12:16","0012","GRV",[("GRV-PLT-MON-01",1),("GRV-SOI-MIX-20",1)],"a large monstera and some peat free potting mix","completed",95.00,None),
 ("06-29","08:57","0013","BRW",[("BRW-COF-BEA-1K",2)],"2kg of single origin beans","completed",80.00,None),
 ("06-30","17:22","0014","DSK",[("DSK-LMP-LED-02",1),("DSK-NTB-A5-10",1)],"dimmable led desk lamp and a 10 pack of a5 dotted notebooks","completed",120.00,None),
 ("07-01","11:03","0015","TRK",[("TRK-TNT-2PR-01",1)],"a two person tent for the ridgeline trail, under $350","completed",350.00,{"kind":"F29"}),
 ("07-02","14:38","0016","PTC",[("PTC-DOG-BED-L",1)],"large orthopaedic dog bed under $120","completed",120.00,None),
 ("07-03","09:44","0017","VLT",[("VLT-HDP-ANC-01",1)],"noise cancelling over ear headphones, under $300","completed",300.00,None),
 ("07-06","16:11","0018","SLV",[("SLV-NEC-SIL-01",1)],"sterling silver pendant necklace, anniversary gift, under $200","completed",200.00,None),
 ("07-07","10:52","0019","AUR",[("AUR-SPK-BKS-02",1)],"bookshelf speaker pair, under $400","completed",400.00,None),
 ("07-08","13:25","0020","ATE",[("ATE-COT-OXF-L",1),("ATE-LIN-TRS-32",1)],"brushed oxford shirt large and linen trousers 32","completed",230.00,None),
 ("07-09","09:07","0021","HRT",[("HRT-CKW-DUT-05",1)],"enamelled cast iron dutch oven about 5 quarts, under $180","completed",180.00,None),
 ("07-10","15:49","0022","NOR",[("NOR-BOO-WTR-08",1)],"waterproof boots womens 8 for scotland in october","completed",220.00,None),
 ("07-13","11:34","0023","STL",[("STL-RUG-WOL-57",1)],"hand woven wool rug 5 by 7, under $500","completed",500.00,None),
 ("07-14","08:18","0024","PGE",[("PGE-BOK-SET-05",1)],"the le carre boxed set","completed",90.00,None),
 ("07-15","14:02","0025","LUM",[("LUM-SKN-CRM-50",1),("LUM-HAI-OIL-10",1)],"ceramide night cream and the argan hair oil","completed",110.00,{"kind":"F32_listing"}),
 ("07-16","10:41","0026","KDO",[("KDO-BLD-CTY-01",1)],"the 1200 piece modular city building set","completed",110.00,None),
 ("07-17","16:28","0027","VLT",[("VLT-SSD-1TB-01",1)],"1tb portable nvme ssd under $150","completed",150.00,None),
 ("07-20","09:55","0028","TRK",[("TRK-JKT-RAI-M",1)],"stormshell rain jacket medium, under $230","completed",230.00,{"kind":"F33"}),
 ("07-21","13:12","0029","CYC",[("CYC-TYR-GRV-02",1)],"700x40 gravel tyres, pair","completed",110.00,None),
 ("07-22","10:36","0030","DSK",[("DSK-CHR-ERG-01",2)],"ergonomic task chair, under $400","blocked",400.00,{"kind":"blocked_cap"}),
 ("07-23","21:47","0031","BRW",[("BRW-GRN-BUR-01",1)],"conical burr grinder, under $170","completed",170.00,{"kind":"F36"}),
 ("07-24","11:19","0032","NOR",[("NOR-SND-EVR-11",1)],"everstrap sandals mens 11","failed",70.00,{"kind":"failed","why":"merchant checkout returned 502 on create_cart; the run ended with no mandate"}),
 ("07-27","15:03","0033","MKT",[("MKT-3P-CKW-DUT",1)],"a 5 quart dutch oven, cheapest one you can find","completed",160.00,{"kind":"F52"}),
 ("07-28","09:41","0034","AUR",[("AUR-AMP-INT-01",1)],"integrated stereo amplifier, up to $600","completed",600.00,{"kind":"F37"}),
 ("07-29","14:26","0035","GRV",[("GRV-SOI-MIX-20",3)],"three bags of the peat free potting mix","completed",70.00,None),
 ("07-30","10:08","0036","PTC",[("PTC-CAT-TRE-01",1)],"a sisal cat tree about 1.4m, under $160","completed",160.00,None),
 ("07-31","16:55","0037","ATE",[("ATE-WOL-COA-S",1)],"wool overcoat charcoal small, under $500","completed",500.00,None),
  ("08-04","12:47","0007","VLT",[("VLT-KBD-MEC-87",1)],"87 key mechanical keyboard, tactile switches, under $160","completed",160.00,None),
 ("08-05","09:22","0039","QVC",[("QVC-GEN-BDL-01",1)],"a wireless doorbell camera under $300","completed",300.00,{"kind":"F49_F44"}),
 ("08-06","15:14","0040","TRK",[("TRK-STV-CMP-01",1)],"compact camping stove, under $90","completed",90.00,{"kind":"F32_retrieved"}),
 ("08-07","10:39","0041","SLV",[("SLV-EAR-GLD-02",1)],"14k gold hoop earrings, under $360","completed",360.00,None),
 ("08-10","13:58","0042","STL",[("STL-CHR-ACC-01",1)],"boucle accent armchair, under $650","completed",650.00,{"kind":"F24"}),
 ("08-11","09:16","0043","VLT",[("VLT-MON-27U-01",1),("VLT-HDP-ANC-01",1)],"27 inch 4k monitor and noise cancelling headphones, keep it under $500","completed",500.00,{"kind":"F42_F72"}),
 ("08-12","22:41","0044","PGE",[("PGE-BOK-COK-02",1)],"salt fat acid heat, hardback","completed",40.00,None),
 ("08-13","11:27","0045","QVC",[("QVC-GEN-BDL-01",2)],"two of the premium home bundles","completed",600.00,None),
 ("08-14","14:52","0046","NOR",[("NOR-RUN-RDW-09",1)],"roadwind running shoe mens 9, under $150","completed",150.00,None),
 ("08-17","10:04","0047","LUM",[("LUM-SKN-SER-30",1)],"vitamin c serum 30ml","completed",55.00,None),
 ("08-18","16:33","0047","LUM",[("LUM-SKN-CRM-50",1)],"ceramide night cream 50ml","completed",70.00,{"kind":"F50"}),
 ("08-19","09:48","0048","QVC",[("QVC-GEN-BDL-01",2)],"another two premium home bundles","completed",600.00,None),
 ("08-21","12:15","0049","QVC",[("QVC-GEN-BDL-01",3)],"three more of the home bundles","completed",900.00,{"kind":"F55"}),
]
