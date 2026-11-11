"""Transformă textul din logo-ul Ascendent (varianta 1, Acoperișul) în contur, ca logo-ul să nu mai depindă de font.

Citește direct fișierele .ttf (fără biblioteci în plus) și scrie fișierele finale în logo/final/.
Folosire: python -I contur_logo.py <SourceSerif4-SemiBold.ttf> <SourceSerif4-Regular.ttf>
"""
import struct
import sys
from pathlib import Path


class Font:
    def __init__(self, cale):
        self.d = Path(cale).read_bytes()
        n = struct.unpack('>H', self.d[4:6])[0]
        self.t = {}
        for i in range(n):
            tag, _, off, ln = struct.unpack('>4sIII', self.d[12 + 16 * i: 28 + 16 * i])
            self.t[tag.decode('latin-1')] = (off, ln)
        h = self.t['head'][0]
        self.upm = struct.unpack('>H', self.d[h + 18:h + 20])[0]
        loc_fmt = struct.unpack('>h', self.d[h + 50:h + 52])[0]
        self.n_glyphs = struct.unpack('>H', self.d[self.t['maxp'][0] + 4:self.t['maxp'][0] + 6])[0]
        n_h = struct.unpack('>H', self.d[self.t['hhea'][0] + 34:self.t['hhea'][0] + 36])[0]
        hm = self.t['hmtx'][0]
        self.adv = [struct.unpack('>H', self.d[hm + 4 * i:hm + 4 * i + 2])[0] for i in range(n_h)]
        lo = self.t['loca'][0]
        if loc_fmt == 0:
            self.loca = [2 * struct.unpack('>H', self.d[lo + 2 * i:lo + 2 * i + 2])[0] for i in range(self.n_glyphs + 1)]
        else:
            self.loca = [struct.unpack('>I', self.d[lo + 4 * i:lo + 4 * i + 4])[0] for i in range(self.n_glyphs + 1)]
        self.cmap = self._cmap()

    def _cmap(self):
        c = self.t['cmap'][0]
        n = struct.unpack('>H', self.d[c + 2:c + 4])[0]
        sub = None
        for i in range(n):
            pid, eid, off = struct.unpack('>HHI', self.d[c + 4 + 8 * i:c + 12 + 8 * i])
            fmt = struct.unpack('>H', self.d[c + off:c + off + 2])[0]
            if pid == 3 and eid in (1, 10) and fmt in (4, 12):
                if sub is None or fmt == 12:
                    sub = (c + off, fmt)
        o, fmt = sub
        m = {}
        if fmt == 12:
            ng = struct.unpack('>I', self.d[o + 12:o + 16])[0]
            for i in range(ng):
                a, b, g = struct.unpack('>III', self.d[o + 16 + 12 * i:o + 28 + 12 * i])
                for cp in range(a, b + 1):
                    m[cp] = g + cp - a
            return m
        segx2 = struct.unpack('>H', self.d[o + 6:o + 8])[0]
        seg = segx2 // 2
        ends = struct.unpack(f'>{seg}H', self.d[o + 14:o + 14 + segx2])
        starts = struct.unpack(f'>{seg}H', self.d[o + 16 + segx2:o + 16 + 2 * segx2])
        deltas = struct.unpack(f'>{seg}h', self.d[o + 16 + 2 * segx2:o + 16 + 3 * segx2])
        ro_off = o + 16 + 3 * segx2
        ranges = struct.unpack(f'>{seg}H', self.d[ro_off:ro_off + segx2])
        for i in range(seg):
            for cp in range(starts[i], ends[i] + 1):
                if cp == 0xFFFF:
                    continue
                if ranges[i] == 0:
                    g = (cp + deltas[i]) & 0xFFFF
                else:
                    a = ro_off + 2 * i + ranges[i] + 2 * (cp - starts[i])
                    g = struct.unpack('>H', self.d[a:a + 2])[0]
                    if g:
                        g = (g + deltas[i]) & 0xFFFF
                m[cp] = g
        return m

    def avans(self, g):
        return self.adv[min(g, len(self.adv) - 1)]

    def contururi(self, g, tr=(1, 0, 0, 1, 0, 0)):
        """Lista de contururi; fiecare contur e o listă de (x, y, pe_curba)."""
        a, b = self.loca[g], self.loca[g + 1]
        if a == b:
            return []
        o = self.t['glyf'][0] + a
        nc = struct.unpack('>h', self.d[o:o + 2])[0]
        p = o + 10
        out = []
        if nc >= 0:
            ends = struct.unpack(f'>{nc}H', self.d[p:p + 2 * nc]); p += 2 * nc
            il = struct.unpack('>H', self.d[p:p + 2])[0]; p += 2 + il
            npts = ends[-1] + 1 if nc else 0
            flags = []
            while len(flags) < npts:
                f = self.d[p]; p += 1
                flags.append(f)
                if f & 8:
                    r = self.d[p]; p += 1
                    flags.extend([f] * r)
            xs, ys = [], []
            for coords, short, same in ((xs, 2, 16), (ys, 4, 32)):
                v = 0
                for f in flags:
                    if f & short:
                        dv = self.d[p]; p += 1
                        v += dv if f & same else -dv
                    elif not f & same:
                        v += struct.unpack('>h', self.d[p:p + 2])[0]; p += 2
                    coords.append(v)
            s = 0
            a_, b_, c_, d_, e_, f_ = tr
            for e in ends:
                out.append([(a_ * xs[i] + c_ * ys[i] + e_, b_ * xs[i] + d_ * ys[i] + f_, bool(flags[i] & 1)) for i in range(s, e + 1)])
                s = e + 1
            return out
        while True:
            fl, gi = struct.unpack('>HH', self.d[p:p + 4]); p += 4
            if fl & 1:
                dx, dy = struct.unpack('>hh', self.d[p:p + 4]); p += 4
            else:
                dx, dy = struct.unpack('>bb', self.d[p:p + 2]); p += 2
            sa, sb, sc, sd = 1, 0, 0, 1
            if fl & 8:
                sa = sd = struct.unpack('>h', self.d[p:p + 2])[0] / 16384; p += 2
            elif fl & 0x40:
                sa, sd = (v / 16384 for v in struct.unpack('>hh', self.d[p:p + 4])); p += 4
            elif fl & 0x80:
                sa, sb, sc, sd = (v / 16384 for v in struct.unpack('>hhhh', self.d[p:p + 8])); p += 8
            if not fl & 2:
                raise ValueError('componentă aliniată pe puncte, nesuportată')
            a_, b_, c_, d_, e_, f_ = tr
            # componenta: x' = sa*x + sc*y + dx ; apoi transformarea părintelui
            nt = (a_ * sa + c_ * sb, b_ * sa + d_ * sb, a_ * sc + c_ * sd, b_ * sc + d_ * sd,
                  a_ * dx + c_ * dy + e_, b_ * dx + d_ * dy + f_)
            out.extend(self.contururi(gi, nt))
            if not fl & 0x20:
                break
        return out


def r(v):
    s = f'{v:.2f}'.rstrip('0').rstrip('.')
    return '0' if s == '-0' else s


def cale_svg(contururi, sc, x0, y0):
    """Contururile TrueType (pătratice) devin un singur „d” SVG, cu y întors."""
    P = lambda pt: (x0 + pt[0] * sc, y0 - pt[1] * sc)
    d = []
    for c in contururi:
        if not c:
            continue
        n = len(c)
        k = next((i for i, pt in enumerate(c) if pt[2]), None)
        if k is None:  # niciun punct pe curbă: pornim de la mijlocul primelor două
            m = ((c[0][0] + c[1][0]) / 2, (c[0][1] + c[1][1]) / 2, True)
            c = [m] + c; n += 1; k = 0
        pts = c[k:] + c[:k]
        sx, sy = P(pts[0]); d.append(f'M{r(sx)} {r(sy)}')
        i = 1
        while i <= n:
            pt = pts[i % n]
            if pt[2]:
                x, y = P(pt); d.append(f'L{r(x)} {r(y)}'); i += 1
            else:
                nx = pts[(i + 1) % n]
                if nx[2]:
                    end = nx; i += 2
                else:
                    end = ((pt[0] + nx[0]) / 2, (pt[1] + nx[1]) / 2, True); i += 1
                cx, cy = P(pt); ex, ey = P(end)
                d.append(f'Q{r(cx)} {r(cy)} {r(ex)} {r(ey)}')
        d.append('Z')
    return ''.join(d)


def text_contur(font, text, x, y, marime, spatiere):
    sc = marime / font.upm
    parti = []
    for ch in text:
        g = font.cmap.get(ord(ch), 0)
        parti.append(cale_svg(font.contururi(g), sc, x, y))
        x += font.avans(g) * sc + spatiere
    return ''.join(parti), x - spatiere


ROSU = '#c8102e'


def logo(semibold, regular, ink, gri, cu_rand=True):
    nume, x_end = text_contur(semibold, 'ASCENDENT', 102, 56 if cu_rand else 64, 40, 6)
    corp = [f'<path d="M8 50 L44 18 L80 50" fill="none" stroke="{ROSU}" stroke-width="9" stroke-linejoin="miter" stroke-linecap="square"/>',
            f'<rect x="37" y="46" width="14" height="14" fill="{ink}"/>',
            f'<path d="M20 54 V80 H68 V54" fill="none" stroke="{ink}" stroke-width="5"/>',
            f'<path fill="{ink}" d="{nume}"/>']
    latime = x_end
    if cu_rand:
        rand, x2 = text_contur(regular, 'AGENȚIE IMOBILIARĂ · IAȘI', 104, 82, 13, 3.6)
        corp.append(f'<path fill="{gri}" d="{rand}"/>')
        latime = max(latime, x2)
    w = int(latime + 10)
    titlu = 'Ascendent, agenție imobiliară, Iași'
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} 96" width="{w}" height="96" role="img" aria-label="{titlu}">\n'
            f'  <title>{titlu}</title>\n  ' + '\n  '.join(corp) + '\n</svg>\n')


if __name__ == '__main__':
    sb, rg = Font(sys.argv[1]), Font(sys.argv[2])
    for f in (sb, rg):
        lipsa = [ch for ch in 'ASCENDENTGȚIMOBLRĂ·Ș' if ch not in ''.join(chr(c) for c in f.cmap)]
        if lipsa:
            sys.exit(f'Fontului îi lipsesc literele: {lipsa}')
    out = Path(__file__).resolve().parent.parent / 'public' / 'logo' / 'final'
    out.mkdir(exist_ok=True)
    fis = {
        'ascendent-logo.svg': logo(sb, rg, '#201e1d', '#605d5d'),
        'ascendent-logo-pe-inchis.svg': logo(sb, rg, '#ffffff', '#c9c6c5'),
        'ascendent-logo-fara-rand.svg': logo(sb, rg, '#201e1d', '#605d5d', cu_rand=False),
        'ascendent-logo-fara-rand-pe-inchis.svg': logo(sb, rg, '#ffffff', '#c9c6c5', cu_rand=False),
    }
    for n, s in fis.items():
        (out / n).write_text(s, encoding='utf-8')
        print(n, len(s) // 1024, 'KB')
