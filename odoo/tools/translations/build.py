"""veron_core/i18n_modules/<module>.po: the module's .pot entries missing in its own fa.po, translated
from the memory (Odoo's and OCA's Persian) or by hand (tr/manual/<module>.json). Placeholders and
HTML tags must be kept; an entry that loses one is left out and reported."""
import glob, json, os, re, sys, polib
S, OUT = sys.argv[1], sys.argv[2]
memory = json.load(open(f"{S}/tr/memory.json"))
# Format markers, the names of HTML tags (their attributes, like a title, may be translated), entities
PLACEHOLDER = re.compile(r"%\(\w+\)[sdf]|%[sdf]|\{\w*\}|</?[\w-]+|\$\{[^}]+\}|&\w+;|t-\w+=\"[^\"]*\"")
problems, written, missing = [], 0, 0
for f in sorted(glob.glob(f"{S}/tr/todo/*.json")):
    m = os.path.basename(f)[:-5]
    manual = {}
    if os.path.isfile(f"{S}/tr/manual/{m}.json"):
        manual = json.load(open(f"{S}/tr/manual/{m}.json"))
    pot = polib.pofile((glob.glob(f"{S}/t/odoo/oca/*/{m}/i18n/{m}.pot") or glob.glob(f"{S}/tr/odoo_pot/{m}/i18n/{m}.pot"))[0])
    wanted = {k for k, _h in json.load(open(f))}
    po = polib.POFile()
    po.metadata = {"Project-Id-Version": "Odoo Server 19.0", "MIME-Version": "1.0",
                   "Content-Type": "text/plain; charset=UTF-8", "Content-Transfer-Encoding": "", "Language": "fa"}
    for e in pot:
        if e.msgid not in wanted:
            continue
        text = manual.get(e.msgid) or memory.get(e.msgid)
        if not text:
            missing += 1
            continue
        a = sorted(PLACEHOLDER.findall(e.msgid))
        b = sorted(PLACEHOLDER.findall(text))
        if a != b:
            problems.append((m, e.msgid[:80], text[:80]))
            continue
        po.append(polib.POEntry(msgid=e.msgid, msgstr=text, occurrences=e.occurrences, comment=e.comment, tcomment=e.tcomment, flags=[x for x in e.flags if x != "fuzzy"]))
    if len(po):
        po.save(f"{OUT}/{m}.po")
        written += len(po)
print("written", written, "not yet translated", missing, "placeholder problems", len(problems))
for p in problems[:30]:
    print("  ", p)

# The web client reads its strings from po files, not the database, and takes them from any module:
# those of the translated OCA modules go into veron_core's own fa.po
core = polib.POFile()
core.metadata = {"Project-Id-Version": "Odoo Server 19.0", "MIME-Version": "1.0",
                 "Content-Type": "text/plain; charset=UTF-8", "Content-Transfer-Encoding": "", "Language": "fa"}
seen = set()
for path in sorted(glob.glob(f"{OUT}/*.po")):
    for e in polib.pofile(path):
        if "odoo-javascript" in (e.comment or "") and e.msgid not in seen:
            seen.add(e.msgid)
            core.append(polib.POEntry(msgid=e.msgid, msgstr=e.msgstr, comment="module: veron_core\nodoo-javascript",
                                      occurrences=[("code:addons/veron_core/static/src/branding.js", "0")]))
# Strings of web templates no translation template lists (inline templates, attributes)
extra = json.load(open(os.path.join(os.path.dirname(OUT), "i18n_web", "extra.json")))
for msgid, msgstr in extra.items():
    if msgid not in seen:
        seen.add(msgid)
        core.append(polib.POEntry(msgid=msgid, msgstr=msgstr, comment="module: veron_core\nodoo-javascript",
                                  occurrences=[("code:addons/veron_core/static/src/branding.js", "0")]))
core.save(os.path.join(os.path.dirname(OUT), "i18n", "fa.po"))
print("web client strings", len(core))
