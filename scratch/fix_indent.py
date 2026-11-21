"""Fix indentation in query_intelligence.py lines 340-357."""
QI_PATH = r'c:\Users\om70c\Downloads\AI_CON_Project_Clean\scripts\query_intelligence.py'

with open(QI_PATH, 'r', encoding='utf-8') as f:
    content = f.read()

bad_target = (
"""        if not location:
            for dist_key, aliases in COMMON_LOCATIONS.items():
            for alias in aliases:
                matched = False
                if any(ord(c) > 127 for c in alias):
                    if alias in q_lower:
                        matched = True
                elif re.search(r"\\b" + re.escape(alias) + r"\\b", q_lower):
                    matched = True

                if matched:
                    location = dist_key.capitalize()
                    if alias in ("alandi", "wagholi", "pimpri", "chinchwad", "पिंपरी", "चिंचवड"):
                        scope_notes = f"Matched locality '{alias.capitalize()}' within Pune district scope."
                    elif alias in ("navi mumbai", "bandra", "andheri", "dadar", "नवी मुंबई"):
                        scope_notes = f"Matched locality '{alias.capitalize()}' within Mumbai metropolitan scope."
                    break
            if location:
                break"""
)

good_replacement = (
"""        if not location:
            for dist_key, aliases in COMMON_LOCATIONS.items():
                for alias in aliases:
                    matched = False
                    if any(ord(c) > 127 for c in alias):
                        if alias in q_lower:
                            matched = True
                    elif re.search(r"\\b" + re.escape(alias) + r"\\b", q_lower):
                        matched = True

                    if matched:
                        location = dist_key.capitalize()
                        if alias in ("alandi", "wagholi", "pimpri", "chinchwad", "पिंपरी", "चिंचवड"):
                            scope_notes = f"Matched locality '{alias.capitalize()}' within Pune district scope."
                        elif alias in ("navi mumbai", "bandra", "andheri", "dadar", "नवी मुंबई"):
                            scope_notes = f"Matched locality '{alias.capitalize()}' within Mumbai metropolitan scope."
                        break
                if location:
                    break"""
)

if bad_target in content:
    content = content.replace(bad_target, good_replacement)
    with open(QI_PATH, 'w', encoding='utf-8') as f:
        f.write(content)
    print("SUCCESS: Fixed indentation in query_intelligence.py")
else:
    print("Could not match bad_target")

