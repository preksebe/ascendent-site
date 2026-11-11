"""Serverul site-ului Ascendent: conturi cu parolă, favorite în cont, panoul agentului, landing page-ul „Casă nouă”.

Pe calculator:      python server.py            (apoi deschizi http://127.0.0.1:8124), cu baza de date locală date/ascendent.db
Pe Vercel:          app.py importă `app` de aici; baza de date e Postgres (Supabase), din variabila DATABASE_URL
Fă un cont agent:   python server.py fa-agent adresa@email.ro   (contul trebuie să existe și să fie confirmat)

Setări (variabile de mediu sau fișierul .env de lângă acest fișier, care nu se urcă pe GitHub):
    DATABASE_URL     adresa bazei Postgres; fără ea se folosește baza locală SQLite
    SECRET_KEY       cheia sesiunilor; obligatorie pe Vercel, local se generează singură în date/.secret_key
    SITE_URL         adresa publică a site-ului, de exemplu https://ascendent-site.vercel.app
    MAIL_MODE        fisier (implicit pe calculator), dezactivat (implicit pe Vercel) sau smtp
    SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, MAIL_FROM   doar pentru MAIL_MODE=smtp
    EMAIL_AGENTIE    unde ajung întrebările clienților
    CONFIRMARE_EMAIL 1 ca să ceară confirmarea adresei la înregistrare
"""
import hashlib
import html
import json
import os
import re
import secrets
import smtplib
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from functools import wraps
from pathlib import Path

from flask import Flask, g, jsonify, redirect, request, send_from_directory, session
from werkzeug.security import check_password_hash, generate_password_hash


_SCURTE = {'a', 'ai', 'al', 'ale', 'am', 'ar', 'au', 'ca', 'că', 'ce', 'cu', 'de', 'din', 'e', 'în', 'îi', 'la', 'le', 'mai',
           'nu', 'o', 'pe', 'pentru', 'prin', 'sau', 'să', 'se', 'și', 'te', 'un', 'vă'}


def fara_orfane(text):
    """Lipește cu spațiu neseparabil cuvintele scurte de cel următor și ultimele două cuvinte, ca textul din emailuri
    să nu lase un cuvânt singur la capăt de rând."""
    cuv = text.split(' ')
    if len(cuv) < 2:
        return text
    out = cuv[0]
    for i, w in enumerate(cuv[1:], start=1):
        precedent = cuv[i - 1].lower().strip('„"(,.')
        ultimul = i == len(cuv) - 1 and len(cuv[i - 1]) + len(w) < 24
        out += (' ' if precedent in _SCURTE or ultimul else ' ') + w
    return out


BAZA = Path(__file__).resolve().parent
PUBLIC = BAZA / 'public'
DATE = BAZA / 'date'
EMAILURI = BAZA / 'emailuri-trimise'


def incarca_env():
    """Citește .env (CHEIE=valoare) în variabilele de mediu, fără să afișeze nimic."""
    f = BAZA / '.env'
    if not f.exists():
        return
    for rand in f.read_text(encoding='utf-8').splitlines():
        rand = rand.strip()
        if not rand or rand.startswith('#') or '=' not in rand:
            continue
        k, v = rand.split('=', 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


incarca_env()
PE_VERCEL = bool(os.environ.get('VERCEL'))
DATABASE_URL = os.environ.get('DATABASE_URL', '').strip()
MAIL_MODE = os.environ.get('MAIL_MODE', 'dezactivat' if PE_VERCEL else 'fisier')


def cheie_sesiuni():
    if os.environ.get('SECRET_KEY'):
        return os.environ['SECRET_KEY']
    if PE_VERCEL:
        raise RuntimeError('Pe Vercel trebuie setată variabila SECRET_KEY.')
    DATE.mkdir(exist_ok=True)
    f = DATE / '.secret_key'
    if not f.exists():
        f.write_text(secrets.token_hex(32), encoding='utf-8')
    return f.read_text(encoding='utf-8').strip()


app = Flask(__name__, static_folder=None)
app.config.update(
    SECRET_KEY=cheie_sesiuni(),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=os.environ.get('SITE_URL', '').startswith('https://'),
    PERMANENT_SESSION_LIFETIME=timedelta(days=30),
)

SITE_URL = os.environ.get('SITE_URL', 'http://127.0.0.1:8124').rstrip('/')
# Confirmarea pe email e oprită deocamdată: contul se activează imediat la înregistrare.
# O pornești din nou cu CONFIRMARE_EMAIL=1 în fișierul .env.
CONFIRMARE = os.environ.get('CONFIRMARE_EMAIL', '0') == '1'
VALABILITATE_LINK = timedelta(hours=24)
PAROLA_MIN = 8
EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')

# Proprietățile de prezentare (aceleași ca în prototip). Numărul de „fani” din prototip nu se mai afișează:
# pe site apare doar câți clienți reali au proprietatea la favorite.
SEED = [
    (1, 'Garsonieră lângă Universitate', 'apartament', 'inchiriere', 'Copou', 1, 32, '2 / 4', 1978, 4, [('2026-09-01', 400), ('2026-11-03', 380)], 'Garsonieră mobilată, la câteva minute de mers pe jos de Universitatea „Alexandru Ioan Cuza”. Liberă din decembrie.'),
    (2, 'Apartament 2 camere, Piața Unirii', 'apartament', 'inchiriere', 'Centru', 2, 52, '3 / 8', 1985, 2, [('2026-10-10', 520)], 'Două camere decomandate, renovat în 2024, centrală proprie.'),
    (3, 'Apartament 3 camere, Tătărași', 'apartament', 'vanzare', 'Tătărași', 3, 68, '1 / 4', 1982, 3, [('2026-08-20', 104000), ('2026-10-28', 98000)], 'Trei camere, două balcoane, aproape de școală și piață. Acte în regulă.'),
    (4, 'Apartament 2 camere, bloc nou', 'apartament', 'vanzare', 'Galata', 2, 55, '4 / 6', 2023, 1, [('2026-10-15', 79500)], 'Bloc finalizat în 2023, loc de parcare inclus.'),
    (5, 'Casă cu curte', 'casa', 'vanzare', 'Valea Lupului', 4, 140, 'P + 1', 2019, 5, [('2026-09-05', 195000), ('2026-11-06', 189000)], 'Casă cu patru camere și teren de 500 m², la 15 minute de centrul Iașului.'),
    (6, 'Teren intravilan 600 m²', 'teren', 'vanzare', 'Miroslava', 0, 600, '—', None, 0, [('2026-10-02', 42000)], 'Teren intravilan cu utilități la limită, deschidere de 18 m.'),
    (7, 'Apartament 1 cameră', 'apartament', 'inchiriere', 'Păcurari', 1, 38, '6 / 10', 1988, 1, [('2026-11-01', 350)], 'O cameră, bucătărie separată, aproape de stația de tramvai.'),
    (8, 'Apartament 3 camere', 'apartament', 'inchiriere', 'Nicolina', 3, 72, '2 / 4', 1980, 2, [('2026-09-15', 550), ('2026-10-20', 600)], 'Trei camere, potrivit pentru familie sau trei studenți.'),
    (9, 'Spațiu comercial stradal', 'spatiu', 'inchiriere', 'Podu Roș', 0, 85, 'Parter', 1990, 0, [('2026-10-25', 1100)], 'Vitrină la stradă, potrivit pentru cabinet, salon sau magazin.'),
    (10, 'Casă 5 camere', 'casa', 'vanzare', 'Bucium', 5, 180, 'P + M', 2015, 2, [('2026-09-28', 245000)], 'Cinci camere, garaj și curte amenajată.'),
    (11, 'Apartament 2 camere', 'apartament', 'vanzare', 'Canta', 2, 48, '3 / 4', 1975, 3, [('2026-10-01', 71000), ('2026-11-07', 68000)], 'Două camere, termopane, bun pentru prima locuință cu credit.'),
    (12, 'Garsonieră', 'apartament', 'vanzare', 'Alexandru cel Bun', 1, 30, '1 / 4', 1979, 1, [('2026-11-05', 46500)], 'Garsonieră cu balcon, potrivită pentru investiție.'),
]


# ---------------- baza de date ----------------

class RandMixt(tuple):
    """Rând din Postgres care se citește și după nume (r['email']), și după poziție (r[0]), ca sqlite3.Row."""
    def __new__(cls, valori, index):
        o = super().__new__(cls, valori)
        o._index = index
        return o

    def __getitem__(self, k):
        return tuple.__getitem__(self, self._index[k] if isinstance(k, str) else k)


def rand_mixt(cursor):
    index = {c.name: i for i, c in enumerate(cursor.description or [])}
    return lambda valori: RandMixt(valori, index)


class Baza:
    """Același cod pentru baza locală (SQLite) și pentru Supabase (Postgres, când e setat DATABASE_URL)."""

    def __init__(self):
        self.pg = bool(DATABASE_URL)
        if self.pg:
            import psycopg
            # prepare_threshold=None: conexiunea prin pooler-ul Supabase nu suportă comenzi pregătite
            self.c = psycopg.connect(DATABASE_URL, row_factory=rand_mixt, prepare_threshold=None, connect_timeout=10)
        else:
            DATE.mkdir(exist_ok=True)
            self.c = sqlite3.connect(DATE / 'ascendent.db')
            self.c.row_factory = sqlite3.Row
            self.c.execute('PRAGMA foreign_keys = ON')

    def _sql(self, q):
        if not self.pg:
            return q
        if q.lstrip().upper().startswith('INSERT OR IGNORE'):
            q = q.replace('INSERT OR IGNORE', 'INSERT', 1) + ' ON CONFLICT DO NOTHING'
        return q.replace('?', '%s')

    def execute(self, q, p=()):
        return self.c.execute(self._sql(q), p)

    def insert_id(self, q, p):
        """INSERT care întoarce id-ul rândului nou."""
        if self.pg:
            return self.c.execute(self._sql(q) + ' RETURNING id', p).fetchone()[0]
        return self.c.execute(q, p).lastrowid

    def commit(self):
        self.c.commit()

    def close(self):
        self.c.close()


def db():
    if 'db' not in g:
        g.db = Baza()
    return g.db


@app.teardown_appcontext
def inchide_db(_):
    c = g.pop('db', None)
    if c is not None:
        c.close()


TABELE = ['users', 'props', 'prices', 'favs', 'intrebari', 'interesati', 'notifs']

SCHEMA_PG = '''
CREATE TABLE IF NOT EXISTS users (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY, email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL,
    phone TEXT DEFAULT '', confirmed INTEGER NOT NULL DEFAULT 0, token_hash TEXT, token_expires TEXT,
    via_email INTEGER NOT NULL DEFAULT 1, via_sms INTEGER NOT NULL DEFAULT 0, is_agent INTEGER NOT NULL DEFAULT 0,
    created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS props (
    id INTEGER PRIMARY KEY, title TEXT, type TEXT, deal TEXT, zone TEXT, rooms INTEGER, area DOUBLE PRECISION, floor TEXT,
    year INTEGER, demo_fans INTEGER, descr TEXT);
CREATE TABLE IF NOT EXISTS prices (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY, prop_id INTEGER NOT NULL REFERENCES props(id),
    date TEXT NOT NULL, price DOUBLE PRECISION NOT NULL);
CREATE TABLE IF NOT EXISTS favs (
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE, prop_id INTEGER NOT NULL REFERENCES props(id),
    PRIMARY KEY (user_id, prop_id));
CREATE TABLE IF NOT EXISTS intrebari (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY, email TEXT NOT NULL, intrebare TEXT NOT NULL,
    campanie TEXT NOT NULL, created TEXT NOT NULL, trimis INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS interesati (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY, email TEXT NOT NULL, campanie TEXT NOT NULL,
    created TEXT NOT NULL, UNIQUE (email, campanie));
CREATE TABLE IF NOT EXISTS notifs (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY, user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    prop_id INTEGER NOT NULL REFERENCES props(id), old_price DOUBLE PRECISION, new_price DOUBLE PRECISION, date TEXT,
    read INTEGER DEFAULT 0);
''' + ''.join(f'ALTER TABLE {t} ENABLE ROW LEVEL SECURITY;\n' for t in TABELE)
# Row Level Security pornit fără reguli: tabelele nu se pot citi prin API-ul public Supabase,
# doar prin conexiunea serverului (rolul postgres), care ocolește aceste reguli.


def sql_seed_pg():
    """Comenzile care pun cele 12 proprietăți de prezentare într-o bază Postgres goală."""
    def lit(v):
        if v is None:
            return 'NULL'
        if isinstance(v, (int, float)):
            return repr(v)
        return "'" + str(v).replace("'", "''") + "'"
    linii = []
    for (pid, title, typ, deal, zone, rooms, area, floor, year, fans, hist, descr) in SEED:
        linii.append('INSERT INTO props (id, title, type, deal, zone, rooms, area, floor, year, demo_fans, descr) VALUES ('
                     + ', '.join(lit(v) for v in (pid, title, typ, deal, zone, rooms, area, floor, year, fans, descr))
                     + ') ON CONFLICT (id) DO NOTHING;')
        for d, p in hist:
            linii.append(f'INSERT INTO prices (prop_id, date, price) SELECT {pid}, {lit(d)}, {p} '
                         f'WHERE NOT EXISTS (SELECT 1 FROM prices WHERE prop_id={pid} AND date={lit(d)});')
    return '\n'.join(linii)


def init_db():
    if DATABASE_URL:
        b = Baza()
        b.c.execute(SCHEMA_PG)
        b.c.execute(sql_seed_pg())
        b.commit()
        b.close()
        return
    DATE.mkdir(exist_ok=True)
    c = sqlite3.connect(DATE / 'ascendent.db')
    c.executescript('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, phone TEXT DEFAULT '',
        confirmed INTEGER NOT NULL DEFAULT 0, token_hash TEXT, token_expires TEXT,
        via_email INTEGER NOT NULL DEFAULT 1, via_sms INTEGER NOT NULL DEFAULT 0, is_agent INTEGER NOT NULL DEFAULT 0,
        created TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS props (
        id INTEGER PRIMARY KEY, title TEXT, type TEXT, deal TEXT, zone TEXT, rooms INTEGER, area REAL, floor TEXT,
        year INTEGER, demo_fans INTEGER, descr TEXT);
    CREATE TABLE IF NOT EXISTS prices (
        id INTEGER PRIMARY KEY, prop_id INTEGER NOT NULL REFERENCES props(id), date TEXT NOT NULL, price REAL NOT NULL);
    CREATE TABLE IF NOT EXISTS favs (
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, prop_id INTEGER NOT NULL REFERENCES props(id),
        PRIMARY KEY (user_id, prop_id));
    CREATE TABLE IF NOT EXISTS intrebari (
        id INTEGER PRIMARY KEY, email TEXT NOT NULL, intrebare TEXT NOT NULL, campanie TEXT NOT NULL,
        created TEXT NOT NULL, trimis INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE IF NOT EXISTS interesati (
        id INTEGER PRIMARY KEY, email TEXT NOT NULL, campanie TEXT NOT NULL, created TEXT NOT NULL,
        UNIQUE (email, campanie));
    CREATE TABLE IF NOT EXISTS notifs (
        id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        prop_id INTEGER NOT NULL REFERENCES props(id), old_price REAL, new_price REAL, date TEXT, read INTEGER DEFAULT 0);
    ''')
    if c.execute('SELECT COUNT(*) FROM props').fetchone()[0] == 0:
        for (pid, title, typ, deal, zone, rooms, area, floor, year, fans, hist, descr) in SEED:
            c.execute('INSERT INTO props VALUES (?,?,?,?,?,?,?,?,?,?,?)', (pid, title, typ, deal, zone, rooms, area, floor, year, fans, descr))
            for d, p in hist:
                c.execute('INSERT INTO prices (prop_id, date, price) VALUES (?,?,?)', (pid, d, p))
    c.commit()
    c.close()


def acum():
    return datetime.now(timezone.utc)


def hash_token(t):
    return hashlib.sha256(t.encode()).hexdigest()


# ---------------- emailuri ----------------

def trimite_email(catre, subiect, text, html_corp, raspuns_la=None):
    """Trimite emailul prin SMTP (MAIL_MODE=smtp), îl salvează ca fișier în emailuri-trimise/ (fisier)
    sau nu face nimic (dezactivat). Întoarce True doar dacă emailul a plecat sau a fost salvat."""
    if MAIL_MODE == 'dezactivat':
        app.logger.info('Email netrimis (MAIL_MODE=dezactivat): %s', subiect)
        return False
    if MAIL_MODE == 'smtp':
        m = EmailMessage()
        m['Subject'] = subiect
        m['From'] = os.environ.get('MAIL_FROM', os.environ.get('SMTP_USER', ''))
        m['To'] = catre
        if raspuns_la:
            m['Reply-To'] = raspuns_la
        m.set_content(text)
        m.add_alternative(html_corp, subtype='html')
        with smtplib.SMTP(os.environ['SMTP_HOST'], int(os.environ.get('SMTP_PORT', '587')), timeout=20) as s:
            s.starttls()
            s.login(os.environ['SMTP_USER'], os.environ['SMTP_PASSWORD'])
            s.send_message(m)
        return True
    EMAILURI.mkdir(exist_ok=True)
    nume =f"{datetime.now().strftime('%Y-%m-%d-%H%M%S')}-{re.sub(r'[^a-z0-9]+', '-', catre.lower()).strip('-')[:60]}.html"
    antet = (f'<div style="font:13px/1.5 system-ui,sans-serif;color:#555;background:#eee;padding:10px 14px">'
             f'Email de test, salvat local, netrimis.<br>Către: {html.escape(catre)}<br>Subiect: {html.escape(subiect)}'
             + (f'<br>„Răspunde” merge la: {html.escape(raspuns_la)}' if raspuns_la else '') + '</div>')
    (EMAILURI / nume).write_text(html_corp.replace('<!--ANTET-->', antet), encoding='utf-8')
    return True


def email_confirmare(email, token):
    link = f'{SITE_URL}/confirmare?token={token}'
    subiect = 'Confirmă adresa de email pentru contul Ascendent'
    p1 = fara_orfane('Bună ziua,')
    p2 = fara_orfane('Ați creat un cont pe site-ul Ascendent. Ca să-l activați, confirmați adresa de email apăsând butonul de mai jos.')
    p3 = fara_orfane('Linkul e valabil 24 de ore. Dacă nu ați creat dumneavoastră contul, ignorați acest email și contul nu va fi activat.')
    text = f'{p1}\n\n{p2}\n\n{link}\n\n{p3}\n\nAscendent, agenție imobiliară, Iași'.replace(' ', ' ')
    corp = f'''<!doctype html><html lang="ro"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{html.escape(subiect)}</title></head>
<body style="margin:0;background:#f3f2f2;font-family:Georgia,'Times New Roman',serif;color:#201e1d"><!--ANTET-->
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f3f2f2"><tr><td align="center" style="padding:32px 16px">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background:#ffffff;border-radius:2px">
<tr><td style="padding:28px 32px 8px;font-size:20px;font-weight:bold">Ascendent</td></tr>
<tr><td style="padding:8px 32px;font-size:16px;line-height:1.6">
<p style="margin:0 0 14px">{p1}</p><p style="margin:0 0 22px">{p2}</p>
<p style="margin:0 0 22px"><a href="{html.escape(link)}" style="display:inline-block;background:#c8102e;color:#ffffff;text-decoration:none;padding:12px 22px;border-radius:2px;font-weight:bold">Confirmă adresa de email</a></p>
<p style="margin:0 0 14px;font-size:14px;color:#555">{fara_orfane('Dacă butonul nu merge, copiați linkul în browser:')}<br><a href="{html.escape(link)}" style="color:#8c0b20;word-break:break-all">{html.escape(link)}</a></p>
<p style="margin:0 0 22px;font-size:14px;color:#555">{p3}</p>
</td></tr>
<tr><td style="padding:16px 32px 28px;font-size:12px;color:#777">Ascendent, agenție imobiliară, Iași</td></tr>
</table></td></tr></table></body></html>'''
    return trimite_email(email, subiect, text, corp)


def suma(n):
    return f'{int(round(n)):,}'.replace(',', '.')


def pret_text(n, deal):
    return f'{suma(n)} € / lună' if deal == 'inchiriere' else f'{suma(n)} €'


def email_pret(email, prop, vechi, nou):
    """Emailul trimis clienților care au proprietatea la favorite, când agentul îi schimbă prețul."""
    scazut = nou < vechi
    procent = round(abs(nou - vechi) / vechi * 100)
    titlu, zona, deal = prop['title'], prop['zone'], prop['deal']
    link = f"{SITE_URL}/?proprietate={prop['id']}"
    link_cont = f'{SITE_URL}/?pagina=favorite'
    subiect = f"{'A scăzut prețul' if scazut else 'S-a schimbat prețul'}: {titlu}, {zona}"
    p1 = 'Bună ziua,'
    p2 = fara_orfane(f'Proprietatea „{titlu}” din {zona}, pe care ați salvat-o la favorite, are un preț nou.')
    nota = fara_orfane('Primiți acest email pentru că aveți proprietatea la favorite pe site-ul Ascendent. Puteți opri aceste emailuri din contul dumneavoastră.')
    semn = '−' if scazut else '+'
    text = (f'{p1}\n\n{p2}\n\nPreț nou: {pret_text(nou, deal)} (înainte: {pret_text(vechi, deal)}, {semn}{procent}%)\n\n'
            f'Vezi proprietatea: {link}\n\n{nota}\nOprești emailurile aici: {link_cont}\n\nAscendent, agenție imobiliară, Iași').replace(' ', ' ')
    culoare = '#8c0b20' if scazut else '#555555'
    corp = f'''<!doctype html><html lang="ro"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{html.escape(subiect)}</title></head>
<body style="margin:0;background:#f3f2f2;font-family:Georgia,'Times New Roman',serif;color:#201e1d"><!--ANTET-->
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f3f2f2"><tr><td align="center" style="padding:32px 16px">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background:#ffffff;border-radius:2px">
<tr><td style="padding:28px 32px 8px;font-size:20px;font-weight:bold">Ascendent</td></tr>
<tr><td style="padding:8px 32px;font-size:16px;line-height:1.6">
<p style="margin:0 0 14px">{p1}</p>
<p style="margin:0 0 18px">{html.escape(p2)}</p>
<p style="margin:0 0 4px;font-size:26px;font-weight:bold">{html.escape(pret_text(nou, deal))}</p>
<p style="margin:0 0 22px;font-size:15px;color:#555"><span style="text-decoration:line-through">{html.escape(pret_text(vechi, deal))}</span>&nbsp;&nbsp;<span style="color:{culoare};font-weight:bold">{semn}{procent}%</span></p>
<p style="margin:0 0 22px"><a href="{html.escape(link)}" style="display:inline-block;background:#c8102e;color:#ffffff;text-decoration:none;padding:12px 22px;border-radius:2px;font-weight:bold">Vezi proprietatea</a></p>
<p style="margin:0 0 22px;font-size:13px;color:#555">{html.escape(nota)} <a href="{html.escape(link_cont)}" style="color:#8c0b20">Setările contului</a></p>
</td></tr>
<tr><td style="padding:16px 32px 28px;font-size:12px;color:#777">Ascendent, agenție imobiliară, Iași</td></tr>
</table></td></tr></table></body></html>'''
    return trimite_email(email, subiect, text, corp)


def email_intrebare(email_client, intrebare):
    """Întrebarea unui client de pe landing page, trimisă agenției. „Răspunde” din email merge direct la client."""
    catre = os.environ.get('EMAIL_AGENTIE', '').strip()
    if not catre:
        if MAIL_MODE == 'smtp':
            raise RuntimeError('EMAIL_AGENTIE nu e setat în .env')
        catre = 'agentia (EMAIL_AGENTIE nesetat)'
    subiect = f'Întrebare despre casa nouă de la {email_client}'
    data = datetime.now().strftime('%d.%m.%Y, %H:%M')
    text = (f'Întrebare de pe pagina „Casă nouă” ({SITE_URL}/casa-noua)\n\nDe la: {email_client}\nData: {data}\n\n'
            f'{intrebare}\n\nCând apăsați „Răspunde”, răspunsul pleacă direct la {email_client}.')
    corp = f'''<!doctype html><html lang="ro"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{html.escape(subiect)}</title></head>
<body style="margin:0;background:#f3f2f2;font-family:Georgia,'Times New Roman',serif;color:#201e1d"><!--ANTET-->
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f3f2f2"><tr><td align="center" style="padding:32px 16px">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background:#ffffff;border-radius:2px">
<tr><td style="padding:28px 32px 8px;font-size:20px;font-weight:bold">Întrebare nouă despre casa nouă</td></tr>
<tr><td style="padding:8px 32px;font-size:16px;line-height:1.6">
<p style="margin:0 0 6px;color:#555;font-size:14px">De la: <a href="mailto:{html.escape(email_client)}" style="color:#8c0b20">{html.escape(email_client)}</a> · {data}</p>
<div style="margin:12px 0 22px;padding:14px 16px;background:#f3f2f2;border-left:4px solid #c8102e;white-space:pre-wrap">{html.escape(intrebare)}</div>
<p style="margin:0 0 22px;font-size:14px;color:#555">{fara_orfane('Când apăsați „Răspunde”, răspunsul pleacă direct la client.')}</p>
</td></tr>
<tr><td style="padding:16px 32px 28px;font-size:12px;color:#777">Trimis de pagina „Casă nouă” a site-ului Ascendent</td></tr>
</table></td></tr></table></body></html>'''
    return trimite_email(catre, subiect, text, corp, raspuns_la=email_client)


def nou_token(user_id):
    t = secrets.token_urlsafe(32)
    db().execute('UPDATE users SET token_hash=?, token_expires=? WHERE id=?',
                 (hash_token(t), (acum() + VALABILITATE_LINK).isoformat(), user_id))
    db().commit()
    return t


# ---------------- ajutoare API ----------------

def eroare(mesaj, cod=400, **extra):
    return jsonify({'ok': False, 'eroare': mesaj, **extra}), cod


def date_json():
    if not request.is_json:
        return None
    return request.get_json(silent=True) or {}


def user_curent():
    uid = session.get('uid')
    if not uid:
        return None
    return db().execute('SELECT * FROM users WHERE id=? AND confirmed=1', (uid,)).fetchone()


def cere_cont(agent=False):
    def dec(f):
        @wraps(f)
        def w(*a, **k):
            u = user_curent()
            if not u:
                return eroare('Intră în cont ca să continui.', 401)
            if agent and not u['is_agent']:
                return eroare('Doar agentul poate face asta.', 403)
            return f(u, *a, **k)
        return w
    return dec


def props_json():
    rows = db().execute('SELECT * FROM props ORDER BY id').fetchall()
    out = []
    for r in rows:
        hist = db().execute('SELECT date, price FROM prices WHERE prop_id=? ORDER BY date, id', (r['id'],)).fetchall()
        real = db().execute('SELECT COUNT(*) FROM favs WHERE prop_id=?', (r['id'],)).fetchone()[0]
        out.append({'id': r['id'], 'title': r['title'], 'type': r['type'], 'deal': r['deal'], 'zone': r['zone'],
                    'rooms': r['rooms'], 'area': r['area'], 'floor': r['floor'], 'year': r['year'], 'desc': r['descr'],
                    'fans': real, 'history': [{'date': h['date'], 'price': h['price']} for h in hist]})
    return out


def me_json(u):
    if not u:
        return {'user': None, 'favs': [], 'notifs': []}
    favs = [r[0] for r in db().execute('SELECT prop_id FROM favs WHERE user_id=?', (u['id'],))]
    notifs = [{'id': n['id'], 'propId': n['prop_id'], 'oldP': n['old_price'], 'newP': n['new_price'], 'date': n['date'], 'read': bool(n['read'])}
              for n in db().execute('SELECT * FROM notifs WHERE user_id=? ORDER BY id DESC LIMIT 50', (u['id'],))]
    return {'user': {'email': u['email'], 'phone': u['phone'], 'viaEmail': bool(u['via_email']), 'viaSms': bool(u['via_sms']),
                     'isAgent': bool(u['is_agent'])}, 'favs': favs, 'notifs': notifs}


# ---------------- pagini ----------------

# Pe Vercel fișierele din public/ sunt servite direct; rutele de mai jos le servesc pe calculator.
@app.get('/')
def acasa():
    return send_from_directory(PUBLIC, 'index.html')


@app.get('/casa-noua')
def landing_casa_noua():
    return send_from_directory(PUBLIC / 'casa-noua', 'index.html')


@app.get('/<path:cale>')
def fisiere(cale):
    if cale.startswith('api/') or any(parte.startswith('.') for parte in cale.split('/')):
        return 'Pagina nu există.', 404
    return send_from_directory(PUBLIC, cale)


@app.get('/confirmare')
def confirmare():
    t = request.args.get('token', '')
    u = db().execute('SELECT * FROM users WHERE token_hash=?', (hash_token(t),)).fetchone() if t else None
    if not u:
        return redirect('/?cont=link-invalid')
    if datetime.fromisoformat(u['token_expires']) < acum():
        return redirect('/?cont=link-expirat')
    db().execute('UPDATE users SET confirmed=1, token_hash=NULL, token_expires=NULL WHERE id=?', (u['id'],))
    db().commit()
    session.clear()
    session.permanent = True
    session['uid'] = u['id']
    return redirect('/?cont=confirmat')


# ---------------- API conturi ----------------

@app.post('/api/inregistrare')
def inregistrare():
    d = date_json()
    if d is None:
        return eroare('Cerere invalidă.')
    email = str(d.get('email', '')).strip().lower()
    parola = str(d.get('parola', ''))
    telefon = str(d.get('telefon', '')).strip()[:30]
    if not EMAIL_RE.match(email) or len(email) > 200:
        return eroare('Adresa de email nu pare corectă.')
    if len(parola) < PAROLA_MIN:
        return eroare(f'Parola trebuie să aibă cel puțin {PAROLA_MIN} caractere.')
    if len(parola) > 200:
        return eroare('Parola e prea lungă.')
    u = db().execute('SELECT * FROM users WHERE email=?', (email,)).fetchone()
    if u and (u['confirmed'] or not CONFIRMARE):
        return eroare('Există deja un cont cu această adresă. Intră în cont.', 409)
    confirmat = 0 if CONFIRMARE else 1
    if u:
        db().execute('UPDATE users SET password_hash=?, phone=?, confirmed=? WHERE id=?',
                     (generate_password_hash(parola), telefon, confirmat, u['id']))
        uid = u['id']
    else:
        uid = db().insert_id('INSERT INTO users (email, password_hash, phone, via_sms, confirmed, created) VALUES (?,?,?,?,?,?)',
                             (email, generate_password_hash(parola), telefon, 1 if telefon else 0, confirmat, acum().isoformat()))
    db().commit()
    if CONFIRMARE:
        email_confirmare(email, nou_token(uid))
        return jsonify({'ok': True, 'intrat': False})
    session.clear()
    session.permanent = True
    session['uid'] = uid
    u = db().execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone()
    return jsonify({'ok': True, 'intrat': True, **me_json(u)})


@app.post('/api/anunta-ma')
def anunta_ma():
    """Emailurile lăsate pe landing page („Anunțați-mă când apare”)."""
    d = date_json()
    if d is None:
        return eroare('Cerere invalidă.')
    email = str(d.get('email', '')).strip().lower()
    if not EMAIL_RE.match(email) or len(email) > 200:
        return eroare('Adresa de email nu pare corectă.')
    intrebare = str(d.get('intrebare', '')).strip()
    if len(intrebare) > 2000:
        return eroare('Întrebarea e prea lungă. Scrieți cel mult 2.000 de caractere.')
    db().execute('INSERT OR IGNORE INTO interesati (email, campanie, created) VALUES (?,?,?)',
                 (email, 'casa-noua', acum().isoformat()))
    if intrebare:
        qid = db().insert_id('INSERT INTO intrebari (email, intrebare, campanie, created) VALUES (?,?,?,?)',
                             (email, intrebare, 'casa-noua', acum().isoformat()))
    db().commit()
    if intrebare:
        try:
            if email_intrebare(email, intrebare):
                db().execute('UPDATE intrebari SET trimis=1 WHERE id=?', (qid,))
                db().commit()
        except Exception as e:  # întrebarea rămâne salvată în baza de date chiar dacă emailul nu pleacă
            app.logger.warning('Întrebarea nu a plecat pe email (%s): %s', type(e).__name__, e)
    return jsonify({'ok': True, 'intrebare': bool(intrebare)})  # același răspuns și dacă adresa era deja pe listă


@app.post('/api/retrimite')
def retrimite():
    d = date_json() or {}
    email = str(d.get('email', '')).strip().lower()
    u = db().execute('SELECT * FROM users WHERE email=? AND confirmed=0', (email,)).fetchone()
    if u:
        email_confirmare(email, nou_token(u['id']))
    return jsonify({'ok': True})  # același răspuns oricum, ca să nu se poată afla ce adrese au cont


@app.post('/api/intrare')
def intrare():
    d = date_json()
    if d is None:
        return eroare('Cerere invalidă.')
    email = str(d.get('email', '')).strip().lower()
    parola = str(d.get('parola', ''))
    u = db().execute('SELECT * FROM users WHERE email=?', (email,)).fetchone()
    if not u or not check_password_hash(u['password_hash'], parola):
        return eroare('Emailul sau parola nu se potrivesc.', 401)
    if not u['confirmed']:
        if CONFIRMARE:
            return eroare('Contul nu e confirmat încă. Deschide emailul de confirmare.', 403, neconfirmat=True)
        db().execute('UPDATE users SET confirmed=1, token_hash=NULL, token_expires=NULL WHERE id=?', (u['id'],))
        db().commit()
        u = db().execute('SELECT * FROM users WHERE id=?', (u['id'],)).fetchone()
    session.clear()
    session.permanent = True
    session['uid'] = u['id']
    return jsonify({'ok': True, **me_json(u)})


@app.post('/api/iesire')
def iesire():
    session.clear()
    return jsonify({'ok': True})


@app.get('/api/date')
def date_site():
    return jsonify({'props': props_json(), 'confirmare': CONFIRMARE, **me_json(user_curent())})


@app.post('/api/preferinte')
@cere_cont()
def preferinte(u):
    d = date_json() or {}
    db().execute('UPDATE users SET via_email=?, via_sms=? WHERE id=?',
                 (1 if d.get('viaEmail') else 0, 1 if d.get('viaSms') else 0, u['id']))
    db().commit()
    return jsonify({'ok': True})


@app.post('/api/favorite/<int:pid>')
@cere_cont()
def favorit(u, pid):
    if not db().execute('SELECT 1 FROM props WHERE id=?', (pid,)).fetchone():
        return eroare('Proprietatea nu există.', 404)
    if db().execute('SELECT 1 FROM favs WHERE user_id=? AND prop_id=?', (u['id'], pid)).fetchone():
        db().execute('DELETE FROM favs WHERE user_id=? AND prop_id=?', (u['id'], pid))
        pus = False
    else:
        db().execute('INSERT INTO favs VALUES (?,?)', (u['id'], pid))
        pus = True
    db().commit()
    return jsonify({'ok': True, 'pus': pus})


@app.post('/api/notificari/citite')
@cere_cont()
def notificari_citite(u):
    db().execute('UPDATE notifs SET read=1 WHERE user_id=?', (u['id'],))
    db().commit()
    return jsonify({'ok': True})


@app.post('/api/agent/pret/<int:pid>')
@cere_cont(agent=True)
def schimba_pret(u, pid):
    d = date_json() or {}
    try:
        nou = float(d.get('pret'))
    except (TypeError, ValueError):
        return eroare('Prețul nu e un număr.')
    if nou <= 0 or nou > 100_000_000:
        return eroare('Prețul nu e valid.')
    ultim = db().execute('SELECT price FROM prices WHERE prop_id=? ORDER BY date DESC, id DESC LIMIT 1', (pid,)).fetchone()
    if not ultim:
        return eroare('Proprietatea nu există.', 404)
    vechi = ultim['price']
    if nou == vechi:
        return eroare('Prețul e același.')
    data = acum().isoformat()
    db().execute('INSERT INTO prices (prop_id, date, price) VALUES (?,?,?)', (pid, data, nou))
    notifica = not (d.get('doarScaderi') and nou > vechi)
    trimise, emailuri, esuate = 0, [], 0
    if notifica:
        rows = db().execute('SELECT u.id, u.email, u.via_email FROM favs f JOIN users u ON u.id = f.user_id '
                            'WHERE f.prop_id=? AND u.confirmed=1', (pid,)).fetchall()
        for r in rows:
            db().execute('INSERT INTO notifs (user_id, prop_id, old_price, new_price, date) VALUES (?,?,?,?,?)', (r['id'], pid, vechi, nou, data))
            trimise += 1
            if r['via_email']:
                emailuri.append(r['email'])
    db().commit()
    prop = db().execute('SELECT * FROM props WHERE id=?', (pid,)).fetchone()
    plecate = 0
    for email in emailuri:
        try:
            if email_pret(email, prop, vechi, nou):
                plecate += 1
        except Exception as e:  # un email care nu pleacă nu oprește schimbarea prețului
            esuate += 1
            app.logger.warning('Emailul de preț nu a plecat (%s): %s', type(e).__name__, e)
    return jsonify({'ok': True, 'notificati': trimise, 'notificat': notifica,
                    'emailuri': plecate, 'emailuriEsuate': esuate})


# ---------------- linia de comandă ----------------

def fa_agent(email):
    c = Baza()
    r = c.execute('UPDATE users SET is_agent=1 WHERE email=? AND confirmed=1', (email.strip().lower(),))
    c.commit()
    print('Gata, contul e acum cont de agent.' if r.rowcount else 'Nu există un cont confirmat cu această adresă.')
    c.close()


def exporta_interesati():
    import csv
    c = Baza()
    rows = [tuple(r) for r in c.execute('SELECT email, campanie, created FROM interesati ORDER BY id').fetchall()]
    c.close()
    DATE.mkdir(exist_ok=True)
    f = DATE / 'interesati.csv'
    with open(f, 'w', newline='', encoding='utf-8-sig') as out:
        w = csv.writer(out, delimiter=';')
        w.writerow(['email', 'campanie', 'data'])
        w.writerows(rows)
    print(f'{len(rows)} adrese salvate în {f}')


if __name__ == '__main__':
    init_db()
    if len(sys.argv) == 3 and sys.argv[1] == 'fa-agent':
        fa_agent(sys.argv[2])
    elif len(sys.argv) == 2 and sys.argv[1] == 'interesati':
        exporta_interesati()
    elif len(sys.argv) == 2 and sys.argv[1] == 'init-db':
        print('Tabelele și proprietățile de prezentare sunt pregătite.')
    else:
        print(f'Site-ul merge la {SITE_URL}  (oprești cu Ctrl+C)')
        app.run(host='127.0.0.1', port=8124, debug=False)
