"""Testes do porte3d. Este módulo traz o acervo sintético (banco SQLite com o esquema real e PNGs minúsculos)."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
from PIL import Image

SCHEMA = Path(__file__).resolve().parents[2] / "acervo" / "schema.sql"


class AcervoSintetico:
    """Banco temporário no esquema do acervo; os PNGs ficam ao lado do banco (caminhos relativos)."""

    def __init__(self, pasta: str | Path):
        self.pasta = Path(pasta)
        self.pasta.mkdir(parents=True, exist_ok=True)
        self.db_path = self.pasta / "acervo.sqlite"
        self.db = sqlite3.connect(self.db_path)
        self.db.executescript(SCHEMA.read_text(encoding="utf-8"))

    def sprite(self, nome: str, quadro: np.ndarray | None = None, scale: int = 2) -> None:
        """Registra o sprite. `quadro` é um RGBA (256,128,4) completo; o recorte salvo é só a caixa do que é opaco."""
        if quadro is None:
            quadro = np.zeros((256, 128, 4), np.uint8)
            quadro[100:140, 40:90] = (120, 120, 120, 255)
        ys, xs = np.nonzero(quadro[..., 3])
        y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
        rel = f"sprites/{nome}.png"
        (self.pasta / "sprites").mkdir(exist_ok=True)
        Image.fromarray(quadro[y0:y1, x0:x1]).save(self.pasta / rel)
        self.db.execute("insert into sprites(name,pack,page,png,width,height,offset_x,offset_y,frame_w,frame_h,scale) "
                        "values (?,?,?,?,?,?,?,?,?,?,?)",
                        (nome, "T.pack", "p", rel, int(x1 - x0), int(y1 - y0), int(x0), int(y0), 128, 256, scale))
        self.db.commit()

    def tile(self, nome: str, tileset: str, idx: int, **props: str) -> None:
        self.db.execute("insert into tiles(name,tileset,idx,source,category) values (?,?,?,?,?)",
                        (nome, tileset, idx, "t.tiles", "moveis"))
        for k, v in props.items():
            self.db.execute("insert into tile_props(name,key,value) values (?,?,?)", (nome, k, v))
        self.db.commit()

    def caixa(self, nome: str, idx: int, mn, mx, t=(0, 0, 0), r=(0, 0, 0)) -> None:
        self.db.execute("insert into geometry(name,shape_idx,shape,tx,ty,tz,rx,ry,rz,min_x,min_y,min_z,max_x,max_y,max_z) "
                        "values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (nome, idx, "box", *t, *r, *mn, *mx))
        self.db.commit()

    def outra(self, nome: str, idx: int, forma: str, raw: str, t=(0, 0, 0), r=(0, 0, 0)) -> None:
        self.db.execute("insert into geometry(name,shape_idx,shape,tx,ty,tz,rx,ry,rz,raw) values (?,?,?,?,?,?,?,?,?,?)",
                        (nome, idx, forma, *t, *r, raw))
        self.db.commit()

    def cilindro(self, nome: str, idx: int, raio: int, altura: int, t=(0, 0, 0), r=(0, 0, 0)) -> None:
        raw = (f"cylinder\n{{\n    translate = {t[0]}x{t[1]}x{t[2]}\n    rotate = {r[0]}x{r[1]}x{r[2]}\n"
               f"    radius1 = {raio}\n    radius2 = {raio}\n    height = {altura}\n}}")
        self.outra(nome, idx, "cylinder", raw, t, r)

    def poligono(self, nome: str, idx: int, pontos, plano="XY", t=(0, 0, 0), r=(0, 0, 0)) -> None:
        pts = " ".join(f"{x}x{y}" for x, y in pontos)
        raw = (f"polygon\n{{\n    translate = {t[0]}x{t[1]}x{t[2]}\n    rotate = {r[0]}x{r[1]}x{r[2]}\n"
               f"    plane = {plano}\n    points = {pts}\n}}")
        self.outra(nome, idx, "polygon", raw, t, r)

    def close(self) -> None:
        self.db.close()
