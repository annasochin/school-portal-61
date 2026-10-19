# -*- coding: utf-8 -*-
"""Извлекает фоновые картинки шаблона и показывает, какой слайд какую использует."""
import re
import zipfile
from pathlib import Path

TPL = Path(r"C:\Users\K6\Documents\Проект по умолчанию\Входящие\Шаблон презентации к защите.pptx")
OUT = Path(r"C:\Users\K6\AppData\Local\Temp\opencode\tpl_media")

OUT.mkdir(parents=True, exist_ok=True)
z = zipfile.ZipFile(TPL)
for n in z.namelist():
    if n.startswith("ppt/media/"):
        (OUT / Path(n).name).write_bytes(z.read(n))
        print(Path(n).name, z.getinfo(n).file_size)

for i in range(1, 10):
    rels = z.read(f"ppt/slides/_rels/slide{i}.xml.rels").decode("utf-8")
    imgs = re.findall(r"media/([^\"/]+)", rels)
    print(f"slide{i}:", imgs)
