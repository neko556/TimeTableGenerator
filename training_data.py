# training_data.py

TRAIN_DATA = [
    # --- Basic Examples ---
    ("Give FAC001 Friday off", {
        "entities": [(5, 11, "FACULTY_ID"), (12, 18, "DAY"), (19, 22, "INTENT")]
    }),
    ("FAC002 is unavailable on Monday", {
        "entities": [(0, 6, "FACULTY_ID"), (10, 21, "INTENT"), (25, 31, "DAY")]
    }),
    ("Make FAC003 off on Tuesday", {
        "entities": [(5, 11, "FACULTY_ID"), (12, 15, "INTENT"), (19, 26, "DAY")]
    }),
    ("I need Wednesday off for FAC004", {
        "entities": [(7, 16, "DAY"), (17, 20, "INTENT"), (25, 31, "FACULTY_ID")]
    }),

    # --- Examples with Variations and Typos ---
    ("FAC005 Thursday of", {
        "entities": [(0, 6, "FACULTY_ID"), (7, 15, "DAY"), (16, 18, "INTENT")]
    }),
    ("Can FAC006 have saturday free", {
        "entities": [(4, 10, "FACULTY_ID"), (16, 24, "DAY"), (25, 29, "INTENT")]
    }),
    ("I want FAC007 to have a holiday on Sunday", {
        "entities": [(7, 13, "FACULTY_ID"), (24, 31, "INTENT"), (35, 41, "DAY")]
    }),
    ("FAC008 should be unavailable on wed", {
        "entities": [(0, 6, "FACULTY_ID"), (17, 28, "INTENT"), (32, 35, "DAY")]
    }),

    # --- More Complex Phrasing ---
    ("Don't schedule FAC009 on Fridays", {
        "entities": [(0, 5, "INTENT"), (15, 21, "FACULTY_ID"), (25, 32, "DAY")]
    }),
    ("For FAC010, please make monday a day off", {
        "entities": [(4, 10, "FACULTY_ID"), (23, 29, "DAY"), (32, 40, "INTENT")]
    }),
    ("FAC011 is on leave next tuesday", {
        "entities": [(0, 6, "FACULTY_ID"), (12, 17, "INTENT"), (23, 30, "DAY")]
    }),
    ("Block out Thursday for faculty member FAC012", {
        "entities": [(10, 18, "DAY"), (37, 43, "FACULTY_ID"), (0, 5, "INTENT")]
    }),
    
    # --- Examples Covering Other Keywords ---
    ("FAC013 needs a break on Saturday", {
        "entities": [(0, 6, "FACULTY_ID"), (15, 20, "INTENT"), (24, 32, "DAY")]
    }),
     ("Please make FAC014 not available on Monday", {
        "entities": [(12, 18, "FACULTY_ID"), (19, 32, "INTENT"), (36, 42, "DAY")]
    }),
    ("Confirming Friday as a holiday for FAC015", {
        "entities": [(12, 18, "DAY"), (24, 31, "INTENT"), (36, 42, "FACULTY_ID")]
    }),
     ("FAC016 is taking the day off on Wednesday", {
        "entities": [(0, 6, "FACULTY_ID"), (22, 25, "INTENT"), (33, 42, "DAY")]
    }),
    
    # --- Final Set of Examples ---
    ("Let's give FAC017 Tuesday off", {
        "entities": [(11, 17, "FACULTY_ID"), (18, 25, "DAY"), (26, 29, "INTENT")]
    }),
    ("FAC018 is free on Monday morning", {
        "entities": [(0, 6, "FACULTY_ID"), (10, 14, "INTENT"), (18, 24, "DAY")]
    }),
    ("We need to block FAC019 for all of Friday", {
        "entities": [(12, 17, "INTENT"), (18, 24, "FACULTY_ID"), (34, 40, "DAY")]
    }),
    ("Mark Saturday as unavailable for FAC020", {
        "entities": [(5, 13, "DAY"), (17, 28, "INTENT"), (33, 39, "FACULTY_ID")]
    }),
]
