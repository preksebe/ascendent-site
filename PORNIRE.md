# Cum pornești site-ul Ascendent

1. Deschide un terminal în acest folder.
2. Scrie `python server.py` și apasă Enter.
3. Deschide în browser http://127.0.0.1:8124
4. Ca să oprești site-ul, apasă Ctrl+C în terminal.

Folosește adresa cu `127.0.0.1`, nu `localhost`: linkul din emailul de confirmare duce la `127.0.0.1`, iar contul rămâne
deschis doar pe adresa pe care ai intrat.

## Ce se întâmplă la înregistrare

- Omul își face cont cu email și parolă (cel puțin 8 caractere) și intră direct în cont.
- Confirmarea pe email e oprită deocamdată. Când vrei s-o pornești, pui `CONFIRMARE_EMAIL=1` în fișierul `.env` și
  repornești serverul. Atunci omul primește un email cu un link valabil 24 de ore și nu poate intra în cont până nu-l deschide.
- Acum emailurile nu pleacă pe internet: se salvează ca fișiere în folderul `emailuri-trimise/`. Le deschizi cu dublu clic.

## Ce se întâmplă când agentul schimbă un preț

- Clienții care au proprietatea la favorite primesc o notificare la clopoțel.
- Primesc și un email cu prețul nou, prețul vechi și butonul „Vezi proprietatea”, dacă au bifa „Email” activă în cont
  (pagina Favorite). Emailul se salvează tot în `emailuri-trimise/`.
- Bifa „SMS / WhatsApp” se salvează, dar încă nu trimite nimic.

## Landing page-ul „Casă nouă”

- Adresa: http://127.0.0.1:8124/casa-noua
- Are trei secțiuni: anunțul cu formularul, casa cu pozele și planul, apoi îndemnul final cu formular.
- Emailurile lăsate acolo se salvează în baza de date. Ca să le vezi, oprești serverul și scrii
  `python server.py interesati`: lista apare în `date/interesati.csv`, care se deschide în Excel.
- Pozele sunt în `public/landing/poze/`, în două mărimi: 800 px pentru telefon și 1600 px pentru ecrane mari.
- În secțiunea de jos clienții pot scrie și o întrebare. Întrebarea se salvează în baza de date și pleacă pe emailul
  setat în `.env` la `EMAIL_AGENTIE`. Când apeși „Răspunde” în email, răspunsul merge la client.
  Atenție: cât timp `MAIL_MODE` nu e `smtp`, emailul se salvează doar ca fișier în `emailuri-trimise/` și nu ajunge în Gmail.

## Logo-urile

- Pagina de prezentare: http://127.0.0.1:8124/logo/prezentare-logo.html
- Fișierele sunt în `public/logo/`: fiecare variantă pentru fond deschis, pentru fond închis și ca iconiță.
- Logo-ul ales e varianta 1, Acoperișul. Versiunile finale, cu literele transformate în contur, sunt în `public/logo/final/`:
  `ascendent-logo.svg` (fond deschis), `ascendent-logo-pe-inchis.svg` (fond închis), aceleași fără rândul de dedesubt
  și `ascendent-iconita.svg`. Pe acestea le dai la tipografie, pe rețele sociale sau altor programe.
- Fontul folosit, Source Serif 4, e în `logo-sursa/font-descarcat/`, descărcat de la Google Fonts. Scriptul `logo-sursa/contur_logo.py`
  reface fișierele finale dacă schimbi ceva la logo.

## Contul de agent

Doar contul de agent poate schimba prețurile din „Panou agent”. Ca să faci un cont de agent:

1. Faci un cont obișnuit pe site și îl confirmi din email.
2. Oprești serverul și scrii `python server.py fa-agent adresa@email.ro`.
3. Pornești din nou serverul.

Conturile de test făcute de Claude sunt în `date/conturi-test.md`.

## Când vrei să trimită emailuri de-adevăratelea

Pui în fișierul `.env`, lângă `server.py`, datele de la serviciul de email (Brevo, Gmail sau altul):

```
MAIL_MODE=smtp
SMTP_HOST=
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
MAIL_FROM=
SITE_URL=http://127.0.0.1:8124
```

## Fișierele

- `server.py`: serverul (conturi, confirmare, favorite, prețuri).
- `public/index.html`: pagina site-ului. `public/casa-noua/index.html`: landing page-ul.
- `Ascendent Imobiliare.original.dc.html`: copia paginii dinainte de modificări.
- `date/ascendent.db`: baza de date. `date/.secret_key`: cheia sesiunilor, nu o da nimănui.
