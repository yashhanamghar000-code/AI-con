"""Fix query_intelligence.py extraction edge cases:
1. Category extraction: check for '<category> category' (e.g. 'GOPENS category') before 'category <word>', and ignore English stopwords like 'while', 'and', 'for', 'or'.
2. Location extraction: prioritize state-wide 'maharashtra' sentinel if present so that queries like 'across all districts of Maharashtra, including Pune, Mumbai...' are treated as state-wide.
3. Branch extraction: avoid false positive on 'it' when it is just the English pronoun (e.g. 'mention it', 'use it', 'about it', 'take it', 'as it', 'if it') or when 'only the exact ...' is requested.
"""

QI_PATH = r'c:\Users\om70c\Downloads\AI_CON_Project_Clean\scripts\query_intelligence.py'

with open(QI_PATH, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Category extraction fix
old_cat_block = (
"""        # 6. Extract Category
        category_raw: Optional[str] = None
        normalized_seat: Optional[str] = None
        m_cat = re.search(r"\\bcategory\\s+([A-Za-z0-9_-]+)\\b", q_lower)
        if m_cat:
            category_raw = m_cat.group(1).upper()
        else:
            for raw_c in CATEGORY_NORMALIZATION:
                if any(ord(c) > 127 for c in raw_c):
                    if raw_c in q_lower:
                        category_raw = raw_c
                        break
                elif re.search(r"\\b" + re.escape(raw_c) + r"\\b", q_lower):
                    category_raw = raw_c.upper()
                    break"""
)

new_cat_block = (
"""        # 6. Extract Category
        category_raw: Optional[str] = None
        normalized_seat: Optional[str] = None
        # First check '<category> category' pattern (e.g., 'GOPENS category')
        m_cat_pre = re.search(r"\\b([A-Za-z0-9_-]+)\\s+category\\b", q_lower)
        # Also check 'category <name>' pattern, avoiding common stopwords like 'while', 'and', 'for'
        m_cat_post = re.search(r"\\bcategory\\s+([A-Za-z0-9_-]+)\\b", q_lower)
        stopwords_cat = {"while", "and", "or", "for", "in", "to", "of", "with", "based", "wise", "quota", "seat"}

        if m_cat_pre and m_cat_pre.group(1).lower() not in stopwords_cat:
            category_raw = m_cat_pre.group(1).upper()
        elif m_cat_post and m_cat_post.group(1).lower() not in stopwords_cat:
            category_raw = m_cat_post.group(1).upper()
        else:
            for raw_c in CATEGORY_NORMALIZATION:
                if any(ord(c) > 127 for c in raw_c):
                    if raw_c in q_lower:
                        category_raw = raw_c
                        break
                elif re.search(r"\\b" + re.escape(raw_c) + r"\\b", q_lower):
                    category_raw = raw_c.upper()
                    break"""
)

if old_cat_block in content:
    content = content.replace(old_cat_block, new_cat_block)
    print("SUCCESS: Category extraction updated")
else:
    # Try normalized CRLF
    old_cat_block_crlf = old_cat_block.replace('\n', '\r\n')
    if old_cat_block_crlf in content:
        content = content.replace(old_cat_block_crlf, new_cat_block.replace('\n', '\r\n'))
        print("SUCCESS (CRLF): Category extraction updated")
    else:
        print("FAILED to match old_cat_block")

# 2. Location extraction fix: Prioritize state-wide sentinel 'maharashtra' if mentioned
old_loc_loop = (
"""        # 7. Extract Location and Geographic Scope
        location: Optional[str] = None
        scope_notes: Optional[str] = None
        for dist_key, aliases in COMMON_LOCATIONS.items():"""
)

new_loc_loop = (
"""        # 7. Extract Location and Geographic Scope
        location: Optional[str] = None
        scope_notes: Optional[str] = None
        # If the user explicitly mentions state-wide or all districts of Maharashtra, prioritize Maharashtra
        if any(re.search(r"\\b" + re.escape(alias) + r"\\b", q_lower) for alias in COMMON_LOCATIONS.get("maharashtra", [])):
            location = "Maharashtra"
        if not location:
            for dist_key, aliases in COMMON_LOCATIONS.items():"""
)

if old_loc_loop in content:
    content = content.replace(old_loc_loop, new_loc_loop)
    print("SUCCESS: Location extraction updated")
else:
    old_loc_loop_crlf = old_loc_loop.replace('\n', '\r\n')
    if old_loc_loop_crlf in content:
        content = content.replace(old_loc_loop_crlf, new_loc_loop.replace('\n', '\r\n'))
        print("SUCCESS (CRLF): Location extraction updated")
    else:
        print("FAILED to match old_loc_loop")

# 3. Branch extraction fix: Avoid matching English pronoun 'it' as Information Technology
old_branch_block = (
"""        # 8. Extract Branches
        preferred_branches: List[str] = []
        for branch_alias, canonical in CANONICAL_BRANCH_MAP.items():
            if re.search(r"\\b" + re.escape(branch_alias) + r"\\b", q_lower):
                if canonical not in preferred_branches:
                    preferred_branches.append(canonical)"""
)

new_branch_block = (
"""        # 8. Extract Branches
        preferred_branches: List[str] = []
        # Check if user explicitly asked for 'only the exact <branch>'
        exact_branch_match = re.search(r"\\bonly\\s+(?:the\\s+)?exact\\s+([A-Za-z0-9\\s/&-]+?)(?:\\s+branch)?(?:\\.|,|;|$|\\n)", q_lower)
        for branch_alias, canonical in CANONICAL_BRANCH_MAP.items():
            # Avoid false positive on English pronoun 'it' unless capitalized in raw query or preceded by tech context
            if branch_alias == "it":
                if not re.search(r"\\b(?:it\\s+branch|branch\\s+it|b\\.tech\\s+it|be\\s+it|information technology|in it|for it branch)\\b", q_lower):
                    continue
            if re.search(r"\\b" + re.escape(branch_alias) + r"\\b", q_lower):
                if canonical not in preferred_branches:
                    preferred_branches.append(canonical)

        # If user explicitly requested only one exact branch, filter to that exact branch
        if exact_branch_match:
            exact_stem = exact_branch_match.group(1).strip()
            for b in preferred_branches:
                if b.lower() in exact_stem or exact_stem in b.lower():
                    preferred_branches = [b]
                    break"""
)

if old_branch_block in content:
    content = content.replace(old_branch_block, new_branch_block)
    print("SUCCESS: Branch extraction updated")
else:
    old_branch_block_crlf = old_branch_block.replace('\n', '\r\n')
    if old_branch_block_crlf in content:
        content = content.replace(old_branch_block_crlf, new_branch_block.replace('\n', '\r\n'))
        print("SUCCESS (CRLF): Branch extraction updated")
    else:
        print("FAILED to match old_branch_block")

with open(QI_PATH, 'w', encoding='utf-8') as f:
    f.write(content)

print("Finished applying updates to query_intelligence.py")

