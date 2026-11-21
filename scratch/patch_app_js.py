"""
Patches frontend/app.js with two fixes:
1. Split monolithic try/catch into separate network-catch + processing-catch so the actual error is shown
2. Upgrade formatMarkdownText to convert backtick code spans, headers, and bullet lists
3. Update loading message to mention expected wait time
4. Update catch block to show actual error details
"""
import re, sys

file = r"c:\Users\om70c\Downloads\AI_CON_Project_Clean\frontend\app.js"

with open(file, "rb") as f:
    raw = f.read()

content = raw.decode("utf-8")

# ─── FIX 1: Upgrade loading bubble text to mention wait time ─────────────────
OLD_LOADING = (
    'const loadingBubble = this.appendChatBubble("assistant", '
    '\'<div style="display: flex; align-items: center; gap: 8px;"><span>Consulting 181,137 historical records...</span> '
    '<span class="badge badge-blue">RAG Active</span></div>\', true);'
)
NEW_LOADING = (
    'const loadingBubble = this.appendChatBubble("assistant", '
    '\'<div style="display: flex; align-items: center; gap: 8px;">'
    '<span>Consulting 181,137 historical records... (may take 15–30 s)</span> '
    '<span class="badge badge-blue">RAG Active</span></div>\', true);'
)
if OLD_LOADING in content:
    content = content.replace(OLD_LOADING, NEW_LOADING)
    print("FIX1 (loading text) applied")
else:
    print("FIX1 NOT matched - skipping")

# ─── FIX 2: Split fetch try/catch ────────────────────────────────────────────
OLD_FETCH = (
    '    try {\r\n'
    '      const resp = await fetch(API_BASE + "/api/chat", {\r\n'
    '        method: "POST",\r\n'
    '        headers: this.getAuthHeaders(),\r\n'
    '        body: JSON.stringify({\r\n'
    '          query,\r\n'
    '          user_id: this.state.user.id,\r\n'
    '          token: this.state.token,\r\n'
    '          stream_context: this.state.profile.selectedStream\r\n'
    '        })\r\n'
    '      });\r\n'
    '      const data = await resp.json();\r\n'
)

NEW_FETCH = (
    '    // Separated network-catch from processing-catch for precise diagnostics\r\n'
    '    let _chatResp, _chatData;\r\n'
    '    try {\r\n'
    '      const ctrl = new AbortController();\r\n'
    '      const tid = setTimeout(() => ctrl.abort(), 120000); // 2-min timeout\r\n'
    '      _chatResp = await fetch(API_BASE + "/api/chat", {\r\n'
    '        method: "POST",\r\n'
    '        headers: this.getAuthHeaders(),\r\n'
    '        signal: ctrl.signal,\r\n'
    '        body: JSON.stringify({\r\n'
    '          query,\r\n'
    '          user_id: this.state.user.id,\r\n'
    '          token: this.state.token,\r\n'
    '          stream_context: this.state.profile.selectedStream\r\n'
    '        })\r\n'
    '      });\r\n'
    '      clearTimeout(tid);\r\n'
    '      _chatData = await _chatResp.json();\r\n'
    '    } catch (netErr) {\r\n'
    '      console.error("Chat API error (network/timeout/parse):", netErr.name, netErr.message, netErr);\r\n'
    '      loadingBubble.remove();\r\n'
    '      this.state.isChatLoading = false;\r\n'
    '      const em = netErr.name === "AbortError"\r\n'
    '        ? "Request timed out. The recommendation engine processes large datasets — please try again."\r\n'
    '        : "Network error (" + netErr.name + "): " + netErr.message + ". Ensure Docker is running at " + API_BASE + " and hard-refresh (Ctrl+Shift+R).";\r\n'
    '      this.appendChatBubble("assistant", "\u26a0\ufe0f " + em);\r\n'
    '      return;\r\n'
    '    }\r\n'
    '    const resp = _chatResp, data = _chatData;\r\n'
    '    try {\r\n'
)

if OLD_FETCH in content:
    content = content.replace(OLD_FETCH, NEW_FETCH)
    print("FIX2 (split try/catch) applied")
else:
    print("FIX2 NOT matched")
    # Debug: show what we have
    idx = content.find('const resp = await fetch(API_BASE + "/api/chat"')
    if idx >= 0:
        print(f"fetch found at {idx}:")
        print(repr(content[idx-20:idx+200]))

# ─── FIX 3: Upgrade catch block to show real error ───────────────────────────
OLD_CATCH = (
    '    } catch (err) {\r\n'
    '      console.warn("Chat API error:", err);\r\n'
    '      loadingBubble.remove();\r\n'
    '      this.state.isChatLoading = false;\r\n'
    '      this.appendChatBubble("assistant", `I am currently operating in offline demonstrator mode. For the query: <i>"${query}"</i>, you can inspect verified cutoff records in the **Cutoff Predictor** tab.`);\r\n'
    '    }'
)
NEW_CATCH = (
    '    } catch (procErr) {\r\n'
    '      console.error("Chat response processing error:", procErr.name, procErr.message, procErr);\r\n'
    '      loadingBubble.remove();\r\n'
    '      this.state.isChatLoading = false;\r\n'
    '      this.appendChatBubble("assistant",\r\n'
    '        "\u26a0\ufe0f Response rendering error: " + procErr.message +\r\n'
    '        "<br/><small>The server returned data but it could not be displayed. Check browser console (F12) for details.</small>"\r\n'
    '      );\r\n'
    '    }'
)
if OLD_CATCH in content:
    content = content.replace(OLD_CATCH, NEW_CATCH)
    print("FIX3 (catch block) applied")
else:
    print("FIX3 NOT matched")
    idx = content.find("offline demonstrator mode")
    if idx >= 0:
        print(f"'offline demonstrator mode' found at {idx}:")
        print(repr(content[idx-100:idx+200]))

# ─── FIX 4: Upgrade formatMarkdownText ───────────────────────────────────────
OLD_FMT = (
    '  formatMarkdownText(text) {\r\n'
    '    if (!text) return "";\r\n'
    '    return text\r\n'
    '      .replace(/\\n\\n/g, "<br/><br/>")\r\n'
    '      .replace(/\\n/g, "<br/>")\r\n'
    '      .replace(/\\*\\*(.*?)\\*\\*/g, "<b>$1</b>")\r\n'
    '      .replace(/\\*(.*?)\\*/g, "<i>$1</i>");\r\n'
    '  },'
)
NEW_FMT = (
    '  formatMarkdownText(text) {\r\n'
    '    if (!text) return "";\r\n'
    '    // Convert backtick code spans to <code> tags (prevents template-literal breakage)\r\n'
    '    text = text.replace(/`([^`\\r\\n]+)`/g, function(m, inner) {\r\n'
    '      return \'<code style="background:#f1f5f9;padding:1px 5px;border-radius:3px;font-family:monospace;font-size:0.82em;">\'\r\n'
    '        + inner.replace(/</g, "&lt;").replace(/>/g, "&gt;") + \'</code>\';\r\n'
    '    });\r\n'
    '    // Convert markdown headers (###, ##, #)\r\n'
    '    text = text.replace(/^#{3}\\s+(.+)$/gm, \'<b style="font-size:1em;display:block;margin-top:8px;color:var(--dark-blue);">$1</b>\');\r\n'
    '    text = text.replace(/^#{2}\\s+(.+)$/gm, \'<b style="font-size:1.05em;display:block;margin-top:10px;color:var(--dark-blue);">$1</b>\');\r\n'
    '    text = text.replace(/^#\\s+(.+)$/gm, \'<b style="font-size:1.1em;display:block;margin-top:12px;color:var(--dark-blue);">$1</b>\');\r\n'
    '    return text\r\n'
    '      .replace(/\\n\\n/g, "<br/><br/>")\r\n'
    '      .replace(/\\n/g, "<br/>")\r\n'
    '      .replace(/\\*\\*(.*?)\\*\\*/gs, "<b>$1</b>")\r\n'
    '      .replace(/\\*(.*?)\\*/gs, "<i>$1</i>")\r\n'
    '      .replace(/^\\s*[-*]\\s+/gm, \'<span style="margin-left:12px;">• </span>\');\r\n'
    '  },'
)
if OLD_FMT in content:
    content = content.replace(OLD_FMT, NEW_FMT)
    print("FIX4 (formatMarkdownText) applied")
else:
    print("FIX4 NOT matched")
    idx = content.find("formatMarkdownText(text)")
    print(f"Function at index: {idx}")
    print(repr(content[idx:idx+300]))

# ─── Write back ──────────────────────────────────────────────────────────────
with open(file, "wb") as f:
    f.write(content.encode("utf-8"))

print("\nAll patches applied. app.js updated.")
# Verify key items
with open(file, "r", encoding="utf-8") as f:
    final = f.read()

checks = [
    ("AbortController in fetch", "AbortController" in final),
    ("netErr catch block", "netErr" in final),
    ("procErr catch block", "procErr" in final),
    ("backtick code span regex", "backtick code spans" in final),
    ("offline mode removed", "offline demonstrator mode" not in final),
    ("formatMarkdownText upgraded", "markdown headers" in final),
]
print("\nVerification:")
for name, ok in checks:
    print(f"  {'✓' if ok else '✗'} {name}")

