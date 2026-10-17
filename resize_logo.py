"""Делает уменьшенные копии логотипа из большого PNG."""
from PIL import Image
from pathlib import Path

folder = Path(__file__).parent / "logo-school-61"
big = Image.open(folder / "logo-school-61-2400.png")
print("Исходный размер:", big.size)
for size in (1024, 512):
    out = folder / f"logo-school-61-{size}.png"
    big.resize((size, size), Image.LANCZOS).save(out, optimize=True)
    print("Создан:", out.name)
