"""Realistic FI/pilot questions with the rule(s) a correct answer must cite. Used by tests + `python tests/eval_questions.py`."""
EVAL = [
    ("LAPL(A) recency requirements", ["FCL.140.A"]),
    ("PPL(A) experience requirements 45 hours flight instruction", ["FCL.210.A"]),
    ("night rating aeroplane training hours", ["FCL.810"]),
    ("flight instructor FI(A) prerequisites hours", ["FCL.915.FI"]),
    ("FI training course", ["FCL.930.FI"]),
    ("IR(A) revalidation within 3 months before expiry", ["FCL.625.A", "FCL.625"]),
    ("MEP class rating proficiency check revalidation", ["FCL.740.A"]),
    ("LAPL extension of privileges to TMG", ["FCL.135.A"]),
    ("differences training variant SEP aeroplane", ["FCL.710"]),
    ("logbook recording of flight time", ["FCL.050"]),
    ("carry passengers 3 take-offs and landings 90 days", ["FCL.060"]),
    ("medical certificate class 2 validity age 40 50", ["MED.A.045"]),
    ("language proficiency expert level 6", ["FCL.055"]),
    ("aerodrome operating minima NCO", ["NCO.OP.110", "NCO.OP.111", "NCO.OP.112"]),
    ("supplemental oxygen use NCO pressure altitude", ["NCO.OP.190"]),
    ("passenger briefing NCO", ["NCO.OP.130"]),
    ("flight preparation weather information NCO", ["NCO.OP.135"]),
    ("VFR at night requirements", ["SERA.5005"]),
    ("minimum height VFR over congested areas", ["SERA.5005"]),
    ("right-of-way converging aircraft", ["SERA.3210"]),
    ("radio communication failure procedures", ["SERA.14083"]),
    ("submission of a flight plan", ["SERA.4001"]),
    ("declared training organisation DTO declaration", ["DTO.GEN.115", "DTO.GEN.110", "DTO.GEN.100"]),
    ("examiner certificate validity revalidation", ["FCL.1025"]),
    ("assessment of competence flight instructor", ["FCL.935"]),
    ("student pilot solo flight", ["FCL.020"]),
    ("aerobatic rating requirements", ["FCL.800"]),
    ("sailplane towing banner towing rating", ["FCL.805"]),
    ("transponder mode S carriage SERA", ["SERA.13001", "SERA.13005", "SERA.6005"]),
    ("fuel planning final reserve VFR day aeroplane NCO", ["NCO.OP.125"]),
]

if __name__ == "__main__":
    import sys
    sys.path.insert(0, "src")
    from easa_regs import server
    ok = 0
    for q, exp in EVAL:
        top = [h["ref"] for h in server.search_easa_rules(q, limit=5)["results"]]
        hit = any(any(t == e or t.startswith(e + "(") for t in top) for e in exp)
        ok += hit
        print(("OK  " if hit else "MISS"), q, "->", top[:5])
    print(f"\n{ok}/{len(EVAL)} top-5 hit rate")
