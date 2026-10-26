"""For each installed OCA module: the msgids of its .pot without a Persian translation in its fa.po.
Writes tr/todo/<module>.json: [[msgid, hint], ...]"""
import json, os, sys, glob, polib
root, out, modules = sys.argv[1], sys.argv[2], sys.argv[3:]
os.makedirs(out, exist_ok=True)
total = 0
for m in modules:
    d = (glob.glob(f"{root}/oca/*/{m}") or glob.glob(f"{root}/../../tr/odoo_pot/{m}") or [None])[0]
    if not d or not os.path.isfile(f"{d}/i18n/{m}.pot"):
        continue
    pot = polib.pofile(f"{d}/i18n/{m}.pot")
    done = {}
    fa = f"{d}/i18n/fa.po" if "/oca/" in d else f"{root}/../../tr/odoo_fa/{m}/i18n/fa.po"
    if os.path.isfile(fa):
        done = {e.msgid: e.msgstr for e in polib.pofile(fa) if e.msgstr}
    todo = []
    for e in pot:
        if not e.msgid or e.msgid in done:
            continue
        hint = ",".join(o[0].split(":")[1] if ":" in o[0] else o[0] for o in e.occurrences[:2])
        todo.append([e.msgid, hint])
    if todo:
        json.dump(todo, open(f"{out}/{m}.json", "w"), ensure_ascii=False, indent=0)
        total += len(todo)
        print(m, len(todo))
print("total", total)
