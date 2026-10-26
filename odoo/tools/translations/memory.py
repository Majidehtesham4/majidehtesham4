"""Translation memory: every msgid -> Persian in Odoo's and OCA's fa.po files (the most frequent
translation when they differ). Then, per module, what is left to translate by hand."""
import collections, glob, json, os, sys, polib
S = sys.argv[1]
votes = collections.defaultdict(collections.Counter)
for po in glob.glob(f"{S}/tr/odoo_fa/*/i18n/fa.po") + glob.glob(f"{S}/t/odoo/oca/*/*/i18n/fa.po"):
    for e in polib.pofile(po):
        if e.msgid and e.msgstr and not e.obsolete and "fuzzy" not in e.flags:
            votes[e.msgid][e.msgstr] += 1
memory = {k: v.most_common(1)[0][0] for k, v in votes.items()}
json.dump(memory, open(f"{S}/tr/memory.json", "w"), ensure_ascii=False)
left = 0
os.makedirs(f"{S}/tr/left", exist_ok=True)
for f in sorted(glob.glob(f"{S}/tr/todo/*.json")):
    m = os.path.basename(f)[:-5]
    rest = [[k, h] for k, h in json.load(open(f)) if k not in memory]
    left += len(rest)
    json.dump(rest, open(f"{S}/tr/left/{m}.json", "w"), ensure_ascii=False, indent=0)
    print(m, len(rest))
print("memory", len(memory), "left", left)
