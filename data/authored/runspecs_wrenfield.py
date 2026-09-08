"""Wrenfield's 24 runs — the intake-demonstration submission.

(date, time, shopper, merchant, [(sku, qty)], request, outcome, stated_max, defect)

Deliberately clean. This dossier exists to be uploaded, not to be found out:
its whole job is to be the honest version of a submission so that a tampered
copy of the SAME submission can be put next to it. If the base carried
defects, a rejection at the door would be ambiguous — the reviewer could not
tell whether intake refused it for the tampering or for the contents.

One shopper abandons at the confirmation and one merchant returns a 502,
because a submission with no failed runs at all is not a realistic one.
"""
R = [
 ("07-01","09:22","W001","NOR",[("NOR-RUN-TRL-10",1)],"white trailflex running shoes, women's 10, under $130","completed",130.00,None),
 ("07-02","13:47","W002","PGE",[("PGE-BOK-COK-02",1)],"salt fat acid heat, hardback","completed",40.00,None),
 ("07-03","10:14","W003","HRT",[("HRT-LIN-TWL-06",1)],"a set of six waffle bath towels","completed",100.00,None),
 ("07-06","15:38","W004","LUM",[("LUM-SKN-SER-30",1)],"vitamin c serum 30ml","completed",55.00,None),
 ("07-07","08:56","W005","GRV",[("GRV-PLT-MON-01",1)],"a large monstera, about 90cm","completed",80.00,None),
 ("07-08","14:03","W006","CYC",[("CYC-LGT-SET-01",1)],"front and rear bike light set","completed",70.00,None),
 ("07-09","11:29","W007","KDO",[("KDO-BLD-CTY-01",1)],"the 1200 piece modular city building set","completed",110.00,None),
 ("07-13","16:41","W008","TRK",[("TRK-STV-CMP-01",1)],"compact camping stove, under $90","completed",90.00,None),
 ("07-14","09:47","W009","DSK",[("DSK-NTB-A5-10",1)],"a 10 pack of a5 dotted notebooks","completed",50.00,None),
 ("07-15","13:12","W010","PTC",[("PTC-DOG-BED-L",1)],"large orthopaedic dog bed, under $120","completed",120.00,None),
 ("07-16","10:35","W011","ATE",[("ATE-COT-OXF-L",1)],"brushed oxford shirt, large, under $100","completed",100.00,None),
 ("07-20","14:58","W012","VLT",[("VLT-SSD-1TB-01",1)],"1tb portable nvme ssd, under $150","completed",150.00,None),
 ("07-21","09:16","W013","NOR",[("NOR-SND-EVR-11",1)],"everstrap sandals mens 11","abandoned",70.00,{"kind":"abandoned","why":"shopper closed the confirmation without approving"}),
 ("07-22","15:24","W014","SLV",[("SLV-NEC-SIL-01",1)],"sterling silver pendant necklace, under $200","completed",200.00,None),
 ("07-27","10:49","W015","BRW",[("BRW-COF-BEA-1K",1)],"1kg of single origin coffee beans","completed",45.00,None),
 ("07-28","13:33","W016","AUR",[("AUR-SPK-BKS-02",1)],"bookshelf speaker pair, under $400","completed",400.00,None),
 ("07-30","09:58","W017","STL",[("STL-RUG-WOL-57",1)],"hand woven wool rug 5 by 7, under $450","completed",450.00,None),
 ("08-03","14:27","W018","TRK",[("TRK-JKT-RAI-M",1)],"stormshell rain jacket, medium, under $230","completed",230.00,None),
 ("08-04","11:05","W019","HRT",[("HRT-KNF-CHF-08",1)],"a forged 8 inch chef knife, under $130","completed",130.00,None),
 ("08-05","15:51","W020","VLT",[("VLT-CAB-USB-03",1)],"a 3 pack of 2m usb-c cables","failed",35.00,{"kind":"failed","why":"merchant checkout returned 502 on create_cart; the run ended with no mandate"}),
 ("08-10","10:18","W021","CYC",[("CYC-HLM-ROD-M",1)],"road helmet, medium, under $140","completed",140.00,None),
 ("08-11","13:44","W022","LUM",[("LUM-SKN-CRM-50",1)],"ceramide night cream 50ml","completed",70.00,None),
 ("08-17","09:31","W023","PGE",[("PGE-BOK-SET-05",1)],"the le carre boxed set","completed",90.00,None),
 ("08-21","14:09","W024","KDO",[("KDO-PLU-BEA-01",1)],"the handmade wool bear","completed",60.00,None),
]
