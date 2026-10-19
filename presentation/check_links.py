# -*- coding: utf-8 -*-
"""Проверка гиперссылок в презентации к защите."""
import re
import zipfile
from pathlib import Path

PPTX = Path(r"C:\Users\K6\Documents\Проект по умолчанию"
            r"\Презентация-к-защите-Цифровая-редакция.pptx")

z = zipfile.ZipFile(PPTX)

for slide in ("slide6", "slide9"):
    xml = z.read(f"ppt/slides/{slide}.xml").decode("utf-8")
    rels = z.read(f"ppt/slides/_rels/{slide}.xml.rels").decode("utf-8")
    rmap = dict(re.findall(
        r'Id="(rId\d+)"[^>]*Target="([^"]+)"[^>]*TargetMode="External"', rels))
    print(f"--- {slide}: внешних связей {len(rmap)}")
    clicks = re.findall(r'hlinkClick r:id="(rId\d+)"', xml)
    print(f"    hlinkClick в слайде: {len(clicks)}")
    for rid in clicks:
        # текст прогона сразу после закрытия rPr
        m = re.search(
            r'hlinkClick r:id="%s"[^>]*/></a:rPr><a:t>([^<]*)</a:t>' % rid,
            xml)
        text = m.group(1) if m else "?"
        target = rmap.get(rid, "НЕТ СВЯЗИ!")
        print(f"    {rid} -> {target}")
        print(f"       текст: {text[:80]}")
        # живость ссылки
        if target.startswith("http"):
            import urllib.request
            req = urllib.request.Request(target, method="HEAD",
                                          headers={"User-Agent": "Mozilla/5.0"})
            try:
                with urllib.request.urlopen(req, timeout=25) as resp:
                    print(f"       HTTP {resp.status} — живая")
            except Exception as e1:
                try:
                    req = urllib.request.Request(
                        target, headers={"User-Agent": "Mozilla/5.0"})
                    with urllib.request.urlopen(req, timeout=25) as resp:
                        print(f"       HTTP {resp.status} (GET) — живая")
                except Exception as e2:
                    print(f"       МЕРТВАЯ: {e2}")
