TRAIN_DATA = [
    # --- Original Examples ---
    (
        "Faculty FAC007 must not work on Tuesdays",
        {"entities": [(8, 14, "FACULTY_ID"), (15, 24, "INTENT"), (32, 40, "DAY_OF_WEEK")]},
    ),
    (
        "I prefer CRS101 not be scheduled in the morning",
        {"entities": [(2, 8, "INTENT"), (9, 15, "COURSE_ID"), (41, 48, "TIME_SLOT")]},
    ),
    (
        "It is required that the senior project is in ROOM203",
        {"entities": [(6, 15, "INTENT"), (21, 37, "COURSE_ID"), (45, 52, "ROOM_ID")]},
    ),
    (
        "Try to avoid the last slot for all Lab courses",
        {"entities": [(0, 11, "INTENT"), (12, 22, "TIME_SLOT"), (31, 34, "COURSE_TYPE")]},
    ),
    
    (
        "Professor FAC101 cannot teach on Fridays",
        {"entities": [(10, 16, "FACULTY_ID"), (17, 23, "INTENT"), (32, 39, "DAY_OF_WEEK")]},
    ),
    (
        "For course PHY202, avoid the 9am time slot",
        {"entities": [(11, 17, "COURSE_ID"), (19, 24, "INTENT"), (29, 41, "TIME_SLOT")]},
    ),
    (
        "The final exam for MAT300 must be in the main auditorium",
        {"entities": [(21, 27, "COURSE_ID"), (28, 35, "INTENT"), (43, 60, "ROOM_ID")]},
    ),
    (
        "Ideally, the AI Ethics seminar is not on Monday",
        {"entities": [(0, 7, "INTENT"), (12, 30, "COURSE_ID"), (41, 47, "DAY_OF_WEEK")]},
    ),
    (
        "Lab courses are forbidden on Wednesday afternoons",
        {"entities": [(0, 3, "COURSE_TYPE"), (12, 21, "INTENT"), (25, 45, "TIME_SLOT")]},
    ),
    (
        "It is a preference that FAC005 doesn't teach Elective courses",
        {"entities": [(6, 16, "INTENT"), (22, 28, "FACULTY_ID"), (41, 49, "COURSE_TYPE")]},
    ),
    (
        "Make sure that CS101 is always in ROOM101",
        {"entities": [(15, 20, "COURSE_ID"), (24, 30, "INTENT"), (34, 41, "ROOM_ID")]},
    ),
    (
        "I would prefer if Professor Jones did not have classes on Friday",
        {"entities": [(2, 14, "INTENT"), (18, 32, "FACULTY_ID"), (52, 58, "DAY_OF_WEEK")]},
    )
]