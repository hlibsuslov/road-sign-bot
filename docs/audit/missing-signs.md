# Missing Norwegian road signs: gap analysis of the bot's sign DB

Checked 2026-11-25. Our DB has 285 records. The official list used here is the current consolidated **skiltforskriften** (FOR-2005-10-07-1219, last amended by FOR-2026-08-12-1625).

## Sources (checked 2026-11-25)

| Source | URL | Use |
|---|---|---|
| Lovdata: skiltforskriften, consolidated, "Sist endret FOR-2026-08-12-1625" | https://lovdata.no/dokument/SF/forskrift/2005-10-07-1219 | Authoritative sign list (§§ 4–20, § 46a). Official sign images are embedded as `https://lovdata.no/static/SF/sf-20051007-1219-<nr>-01.gif` (the URL resolves with HTTP 200) |
| Lovtidend amendment texts | https://lovdata.no/dokument/LTI/forskrift/2020-01-30-91, …/2021-05-07-1453, …/2022-05-30-933, …/2022-12-22-2460, …/2024-07-22-1801, …/2026-08-12-1625 | Signs that were added or renamed 2020–2026 |
| Statens vegvesen: Trafikkskilt (overview page, links each chapter to Lovdata) | https://www.vegvesen.no/trafikkinformasjon/vei-og-skilt/trafikkskilt-og-henvendelser/trafikkskilt/ | Cross-check. The page renders with JS and has no machine-readable list or image files |
| Statens vegvesen: Håndbok N300 Trafikkskilt | https://www.vegvesen.no/fag/publikasjoner/handboker/vegnormalene/n300/ | Technical variants (e.g. 930 Sperremarkering exists only in N300) |
| Statens vegvesen hearing on piloting new signs (2026) | https://www.vegvesen.no/fag/publikasjoner/hoeringer/25-323007-endringer-i-skiltforskriften/ | Background for the § 46a trial signs |
| Wikimedia Commons, Category:SVG road signs in Norway (API, 316 files) | https://commons.wikimedia.org/wiki/Category:SVG_road_signs_in_Norway | SVG sources. Our DB variant ids (531_102, 532_H02 …) follow Commons naming |
| no.wikipedia "Liste over norske trafikkskilt" | https://no.wikipedia.org/wiki/Liste_over_norske_trafikkskilt | **The page does not exist** (checked), so there was no Wikipedia cross-check |

Method:
- Every sign number and sub-number in §§ 4, 6, 8, 10, 12, 12b, 14, 16, 18, 20 and 46a was compared with our ids. The letter-O typo in 902_OH etc. was normalised to 0.
- Variants that only change a value (speeds on 362/364, examples for 530–539, 822, 817) were not counted as separate signs.
- Road markings (1000-series) and signals (1080-series) are outside the 100–900 scope.

## Recent changes 2020–2026 (from Lovtidend)

- **2020-01-30 nr. 91**: new 151 *Militær aktivitet*, 650.22 *Sykkelløype*, 790.16 *Kjøpesenter*; text of 306.3 changed.
- **2021-05-07 nr. 1453** (in force 18.05.2021), the el-sparkesykkel package: new 306.10, 367, 369, 377, 379, 380, 382 and 807.10. They were first worded «små elektriske kjøretøy».
- **2022-05-30 nr. 933** (in force 15.06.2022): all of these were renamed to «**liten elektrisk motorvogn**». The titles of 306.1, 306.6 and 306.8 changed. 302 now allows cycling and el-sparkesykkel on fortau. Signs 520/521/522/826 now include fører av liten elektrisk motorvogn.
- **2022-12-22 nr. 2460**: new underskilt 856 *Generell fartsgrense i miniatyr* (used with 556.2 strekningsmåling).
- **2024-07-22 nr. 1801**: new serviceskilt 638 *Døgnhvileplass* (and road marking 1055 Bildeling).
- **2026-08-12 nr. 1625**: new § 46a for **trials only**, covering underskilt 840.1–840.4 «Syklende tillatt på rødt» and markings 1030.
- **Not in the regulation** as of 2026-11-25:
  - *sykkelgate*.
  - *miljøsone / lavutslippssone*: low-emission zones are signed with 560 opplysningstavle or local text and have no sign number of their own.
  - *fartsgrensesone for sykkel*: only a hearing proposal so far.

## Missing signs (68)

Relevance: **high** = core, commonly asked in teoriprøven klasse B. **medium** = can be asked, useful. **low** = specialist or rare.

| Nr | Official Norwegian name | Category | Exam relevance | Note | Official image / SVG |
|---|---|---|---|---|---|
| 151 | Militær aktivitet | fareskilt | low | ny 2020 (FOR-2020-01-30-91) | [Lovdata](https://lovdata.no/static/SF/sf-20051007-1219-151-01.gif) / [Commons SVG](https://commons.wikimedia.org/wiki/File%3ANO_road_sign_151.svg) |
| 306.0 | Forbudt for alle kjøretøy | forbudsskilt | high |  | [Lovdata](https://lovdata.no/static/SF/sf-20051007-1219-306-0-01.gif) / [Commons SVG](https://commons.wikimedia.org/wiki/File%3ANO_road_sign_306.0.svg) |
| 306.1 | Forbudt for motorvogn med unntak av liten elektrisk motorvogn | forbudsskilt | high | tittel endret 2022 | [Lovdata](https://lovdata.no/static/SF/sf-20051007-1219-306-1-01.gif) / [Commons SVG](https://commons.wikimedia.org/wiki/File%3ANO_road_sign_306.1.svg) |
| 306.3 | Forbudt for alle traktorer og for motorredskap konstruert for fart mindre enn 40 km/t | forbudsskilt | medium | tekst endret 2020 | [Lovdata](https://lovdata.no/static/SF/sf-20051007-1219-306-3-01.gif) / [Commons SVG](https://commons.wikimedia.org/wiki/File%3ANO_road_sign_306.3.svg) |
| 306.4 | Forbudt for motorsykkel og moped | forbudsskilt | medium |  | [Lovdata](https://lovdata.no/static/SF/sf-20051007-1219-306-4-01.gif) / [Commons SVG](https://commons.wikimedia.org/wiki/File%3ANO_road_sign_306.4.svg) |
| 306.5 | Forbudt for lastebil og trekkbil | forbudsskilt | medium |  | [Lovdata](https://lovdata.no/static/SF/sf-20051007-1219-306-5-01.gif) / [Commons SVG](https://commons.wikimedia.org/wiki/File%3ANO_road_sign_306.5.svg) |
| 306.6 | Forbudt for syklende og fører av liten elektrisk motorvogn | forbudsskilt | high | tittel endret 2022 | [Lovdata](https://lovdata.no/static/SF/sf-20051007-1219-306-6-01.gif) / [Commons SVG](https://commons.wikimedia.org/wiki/File%3ANO_road_sign_306.6.svg) |
| 306.7 | Forbudt for gående | forbudsskilt | medium |  | [Lovdata](https://lovdata.no/static/SF/sf-20051007-1219-306-7-01.gif) / [Commons SVG](https://commons.wikimedia.org/wiki/File%3ANO_road_sign_306.7.svg) |
| 306.8 | Forbudt for gående, syklende og fører av liten elektrisk motorvogn | forbudsskilt | medium | tittel endret 2022 | [Lovdata](https://lovdata.no/static/SF/sf-20051007-1219-306-8-01.gif) / [Commons SVG](https://commons.wikimedia.org/wiki/File%3ANO_road_sign_306.8.svg) |
| 306.9 | Forbudt for ridende | forbudsskilt | low |  | [Lovdata](https://lovdata.no/static/SF/sf-20051007-1219-306-9-01.gif) / [Commons SVG](https://commons.wikimedia.org/wiki/File%3ANO_road_sign_306.9.svg) |
| 306.10 | Forbudt for liten elektrisk motorvogn | forbudsskilt | medium | ny 2021 (el-sparkesykkel) | [Lovdata](https://lovdata.no/static/SF/sf-20051007-1219-306-10-01.png) / [Commons SVG](https://commons.wikimedia.org/wiki/File%3ANO_road_sign_306.10.svg) |
| 408 | Påbudt kjøreretning i rundkjøring | påbudsskilt | medium |  | [Lovdata](https://lovdata.no/static/SF/sf-20051007-1219-408-01.gif) / [Commons SVG](https://commons.wikimedia.org/wiki/File%3ANO_road_sign_408.svg) |
| 512 | Holdeplass for buss | opplysningsskilt | high |  | [Lovdata](https://lovdata.no/static/SF/sf-20051007-1219-512-01.gif) / [Commons SVG](https://commons.wikimedia.org/wiki/File%3ANO_road_sign_512.svg) |
| 513 | Holdeplass for sporvogn | opplysningsskilt | medium |  | [Lovdata](https://lovdata.no/static/SF/sf-20051007-1219-513-01.gif) / [Commons SVG](https://commons.wikimedia.org/wiki/File%3ANO_road_sign_513.svg) |
| 514 | Holdeplass for drosje | opplysningsskilt | medium |  | [Lovdata](https://lovdata.no/static/SF/sf-20051007-1219-514-01.gif) / [Commons SVG](https://commons.wikimedia.org/wiki/File%3ANO_road_sign_514.svg) |
| 524 | Møteplass | opplysningsskilt | high |  | [Lovdata](https://lovdata.no/static/SF/sf-20051007-1219-524-01.gif) / [Commons SVG](https://commons.wikimedia.org/wiki/File%3ANO_road_sign_524.svg) |
| 555 | Havarilomme | opplysningsskilt | medium |  | [Lovdata](https://lovdata.no/static/SF/sf-20051007-1219-555-01.gif) / [Commons SVG](https://commons.wikimedia.org/wiki/File%3ANO_road_sign_555.svg) |
| 556.1 | Automatisk trafikkontroll – punktmåling | opplysningsskilt | high |  | [Lovdata](https://lovdata.no/static/SF/sf-20051007-1219-556-1-01.gif) / [Commons SVG](https://commons.wikimedia.org/wiki/File%3ANO_road_sign_556.1.svg) |
| 560 | Opplysningstavle (generisk; DB har bare eksempel 560_2) | opplysningsskilt | medium |  | [Lovdata](https://lovdata.no/static/SF/sf-20051007-1219-560-01.gif) / [Commons SVG](https://commons.wikimedia.org/wiki/File%3ANO_road_sign_560.1.svg) |
| 590 | Trafikksikkerhetsinformasjon | opplysningsskilt (kap. 6a) | low |  | [Lovdata](https://lovdata.no/static/SF/sf-20051007-1219-590-01.jpg) |
| 638 | Døgnhvileplass | serviceskilt | low | ny 2024 (FOR-2024-07-22-1801) | [Lovdata](https://lovdata.no/static/SF/sf-20051007-1219-638-01-01.png) |
| 640.10 | Severdighet | serviceskilt | low |  | [Lovdata](https://lovdata.no/static/SF/sf-20051007-1219-640-10-01.gif) / [Commons SVG](https://commons.wikimedia.org/wiki/File%3ANO_road_sign_640.10.svg) |
| 640.12 | Museum/galleri | serviceskilt | low |  | [Lovdata](https://lovdata.no/static/SF/sf-20051007-1219-640-12-01.gif) / [Commons SVG](https://commons.wikimedia.org/wiki/File%3ANO_road_sign_640.12.svg) |
| 640.20 | Utsiktspunkt | serviceskilt | low |  | [Lovdata](https://lovdata.no/static/SF/sf-20051007-1219-640-20-01.gif) / [Commons SVG](https://commons.wikimedia.org/wiki/File%3ANO_road_sign_640.20.svg) |
| 640.30 | Naturvernområde | serviceskilt | low |  | [Lovdata](https://lovdata.no/static/SF/sf-20051007-1219-640-30-02.png) / [Commons SVG](https://commons.wikimedia.org/wiki/File%3ANO_road_sign_640.30.svg) |
| 640.101 | Verdensarv | serviceskilt | low |  | [Lovdata](https://lovdata.no/static/SF/sf-20051007-1219-640-101-01.png) / [Commons SVG](https://commons.wikimedia.org/wiki/File%3ANO_road_sign_640.101.svg) |
| 640.102 | Nasjonale festningsverk | serviceskilt | low |  | [Lovdata](https://lovdata.no/static/SF/sf-20051007-1219-640-102-01.png) / [Commons SVG](https://commons.wikimedia.org/wiki/File%3ANO_road_sign_640.102.svg) |
| 650.10 | Badeplass | serviceskilt | low |  | [Lovdata](https://lovdata.no/static/SF/sf-20051007-1219-650-10-01.gif) / [Commons SVG](https://commons.wikimedia.org/wiki/File%3ANO_road_sign_650.10.svg) |
| 650.11 | Fiskeplass | serviceskilt | low |  | [Lovdata](https://lovdata.no/static/SF/sf-20051007-1219-650-11-01.gif) / [Commons SVG](https://commons.wikimedia.org/wiki/File%3ANO_road_sign_650.11.svg) |
| 650.20 | Tursti | serviceskilt | low |  | [Lovdata](https://lovdata.no/static/SF/sf-20051007-1219-650-20-01.gif) / [Commons SVG](https://commons.wikimedia.org/wiki/File%3ANO_road_sign_650.20.svg) |
| 650.21 | Skiløype | serviceskilt | low |  | [Lovdata](https://lovdata.no/static/SF/sf-20051007-1219-650-21-01.gif) / [Commons SVG](https://commons.wikimedia.org/wiki/File%3ANO_road_sign_650.21.svg) |
| 650.22 | Sykkelløype | serviceskilt | low | ny 2020 | [Lovdata](https://lovdata.no/static/SF/sf-20051007-1219-650-22-01.gif) / [Commons SVG](https://commons.wikimedia.org/wiki/File%3ANO_road_sign_650.22.svg) |
| 650.40 | Gardsmat/bygdeturisme | serviceskilt | low |  | [Lovdata](https://lovdata.no/static/SF/sf-20051007-1219-650-40-01.gif) / [Commons SVG](https://commons.wikimedia.org/wiki/File%3ANO_road_sign_650.40.svg) |
| 650.41 | Olavsrosa | serviceskilt | low |  | [Lovdata](https://lovdata.no/static/SF/sf-20051007-1219-650-41-01.png) / [Commons SVG](https://commons.wikimedia.org/wiki/File%3ANO_road_sign_650.41.svg) |
| 701 | Tabellorienteringstavle | vegvisningsskilt | low |  | [Lovdata](https://lovdata.no/static/SF/sf-20051007-1219-701-01.gif) |
| 703 | Diagramorienteringstavle | vegvisningsskilt | low |  | [Lovdata](https://lovdata.no/static/SF/sf-20051007-1219-703-01.gif) |
| 705 | Avkjøringstavle | vegvisningsskilt | low |  | [Lovdata](https://lovdata.no/static/SF/sf-20051007-1219-705-01.gif) |
| 707 | Kjørefeltorienteringstavle | vegvisningsskilt | medium | feltvalg før kryss | [Lovdata](https://lovdata.no/static/SF/sf-20051007-1219-707-01.gif) |
| 709 | Portalorienteringstavle | vegvisningsskilt | low |  | [Lovdata](https://lovdata.no/static/SF/sf-20051007-1219-709-01.gif) |
| 711 | Tabellvegviser | vegvisningsskilt | low |  | [Lovdata](https://lovdata.no/static/SF/sf-20051007-1219-711-01.gif) |
| 713 | Vanlig vegviser | vegvisningsskilt | medium | fargekoder (blå/gul/hvit/brun/oransje) spørres | [Lovdata](https://lovdata.no/static/SF/sf-20051007-1219-713-01.gif) |
| 715 | Avkjøringsvegviser | vegvisningsskilt | low |  | [Lovdata](https://lovdata.no/static/SF/sf-20051007-1219-715-01.gif) |
| 717 | Kjørefeltvegviser | vegvisningsskilt | medium | feltvalg | [Lovdata](https://lovdata.no/static/SF/sf-20051007-1219-717-01.gif) |
| 719 | Portalvegviser | vegvisningsskilt | low |  | [Lovdata](https://lovdata.no/static/SF/sf-20051007-1219-719-01.gif) |
| 723.31 | Nasjonal turistveg | vegvisningsskilt | low |  | [Lovdata](https://lovdata.no/static/SF/sf-20051007-1219-723-31-01.gif) / [Commons SVG](https://commons.wikimedia.org/wiki/File%3ANO_road_sign_723.31.svg) |
| 725 | Avstandsskilt | vegvisningsskilt | low |  | [Lovdata](https://lovdata.no/static/SF/sf-20051007-1219-725-01.gif) |
| 727 | Stedsnavnskilt | vegvisningsskilt | medium | vanlig felle: angir ikke tettbygd strøk/fartsgrense | [Lovdata](https://lovdata.no/static/SF/sf-20051007-1219-727-01.gif) / [Commons SVG](https://commons.wikimedia.org/wiki/File%3ANO_road_sign_727.3R.svg) |
| 729 | Gate-/vegnavnskilt | vegvisningsskilt | low |  | [Lovdata](https://lovdata.no/static/SF/sf-20051007-1219-729-01.gif) |
| 790.10 | Kirke | vegvisningsskilt (symbol) | low |  | [Lovdata](https://lovdata.no/static/SF/sf-20051007-1219-790-10-01.gif) / [Commons SVG](https://commons.wikimedia.org/wiki/File%3ANO_road_sign_790.10.svg) |
| 790.15 | Næringsområde | vegvisningsskilt (symbol) | low |  | [Lovdata](https://lovdata.no/static/SF/sf-20051007-1219-790-15-01.gif) / [Commons SVG](https://commons.wikimedia.org/wiki/File%3ANO_road_sign_790.15.svg) |
| 790.16 | Kjøpesenter | vegvisningsskilt (symbol) | low | ny 2020 | [Lovdata](https://lovdata.no/static/SF/sf-20051007-1219-790-16-01.gif) |
| 790.20 | Svømmehall | vegvisningsskilt (symbol) | low |  | [Lovdata](https://lovdata.no/static/SF/sf-20051007-1219-790-20-01.gif) / [Commons SVG](https://commons.wikimedia.org/wiki/File%3ANO_road_sign_790.20.svg) |
| 790.30 | Alpinanlegg | vegvisningsskilt (symbol) | low |  | [Lovdata](https://lovdata.no/static/SF/sf-20051007-1219-790-30-01.gif) / [Commons SVG](https://commons.wikimedia.org/wiki/File%3ANO_road_sign_790.30.svg) |
| 790.31 | Hoppbakke | vegvisningsskilt (symbol) | low |  | [Lovdata](https://lovdata.no/static/SF/sf-20051007-1219-790-31-01.gif) / [Commons SVG](https://commons.wikimedia.org/wiki/File%3ANO_road_sign_790.31.svg) |
| 790.32 | Skistadion | vegvisningsskilt (symbol) | low |  | [Lovdata](https://lovdata.no/static/SF/sf-20051007-1219-790-32-01.gif) / [Commons SVG](https://commons.wikimedia.org/wiki/File%3ANO_road_sign_790.32.svg) |
| 790.40 | Golfbane | vegvisningsskilt (symbol) | low |  | [Lovdata](https://lovdata.no/static/SF/sf-20051007-1219-790-40-01.gif) / [Commons SVG](https://commons.wikimedia.org/wiki/File%3ANO_road_sign_790.40.svg) |
| 792.31 | Betaling med AutoPASS | vegvisningsskilt (symbol) | low |  | [Lovdata](https://lovdata.no/static/SF/sf-20051007-1219-792-31-01.gif) / [Commons SVG](https://commons.wikimedia.org/wiki/File%3ANO_road_sign_792.31.svg) |
| 802 | Avstand | underskilt | high |  | [Lovdata](https://lovdata.no/static/SF/sf-20051007-1219-802-01.gif) / [Commons SVG](https://commons.wikimedia.org/wiki/File%3ANorwegian-road-sign-802.0.svg) |
| 804 | Utstrekning | underskilt | high |  | [Lovdata](https://lovdata.no/static/SF/sf-20051007-1219-804-01.gif) / [Commons SVG](https://commons.wikimedia.org/wiki/File%3ANorwegian-road-sign-804.0.svg) |
| 807.10 | Liten elektrisk motorvogn (symbol) | underskilt | medium | ny 2021 | [Lovdata](https://lovdata.no/static/SF/sf-20051007-1219-807-10-01.png) |
| 808 | Tekst | underskilt | medium |  | [Lovdata](https://lovdata.no/static/SF/sf-20051007-1219-808-01.gif) / [Commons SVG](https://commons.wikimedia.org/wiki/File%3ANO_road_sign_808.317B.svg) |
| 810 | Svingpil | underskilt | medium |  | [Lovdata](https://lovdata.no/static/SF/sf-20051007-1219-810-01.gif) / [Commons SVG](https://commons.wikimedia.org/wiki/File%3ANO_road_sign_810.H135.svg) |
| 856 | Generell fartsgrense i miniatyr | underskilt | low | ny 2022 (FOR-2022-12-22-2460), brukes med 556.2 | [Lovdata](https://lovdata.no/static/SF/sf-20051007-1219-856-01.png) |
| 840.1 | Sykling til høyre tillatt («Syklende tillatt på rødt») | underskilt (utprøving § 46a) | low | ny 2026 (FOR-2026-08-12-1625), kun forsøk | [Lovdata](https://lovdata.no/static/SF/sf-20051007-1219-840-1-01.png) |
| 840.2 | Sykling rett frem tillatt («Syklende tillatt på rødt») | underskilt (utprøving § 46a) | low | ny 2026, kun forsøk | [Lovdata](https://lovdata.no/static/SF/sf-20051007-1219-840-2-01.png) |
| 840.3 | Sykling til høyre tillatt («Syklende tillatt på rødt») | underskilt (utprøving § 46a) | low | ny 2026, kun forsøk | [Lovdata](https://lovdata.no/static/SF/sf-20051007-1219-840-3-01.png) |
| 840.4 | Sykling rett frem tillatt («Syklende tillatt på rødt») | underskilt (utprøving § 46a) | low | ny 2026, kun forsøk | [Lovdata](https://lovdata.no/static/SF/sf-20051007-1219-840-4-01.png) |
| 920VE | Kantstolpe (variant VE) | markeringsskilt | low |  | [Lovdata](https://lovdata.no/static/SF/sf-20051007-1219-920VE-01.gif) |

## Counts of missing signs

| Category | Missing |
|---|---|
| 100 fareskilt | 1 |
| 200 vikepliktskilt | 0 |
| 300 forbudsskilt | 10 (the whole 306 *Trafikkforbud* family) |
| 400 påbudsskilt | 1 |
| 500 opplysningsskilt (incl. 590) | 8 |
| 600 serviceskilt | 14 |
| 700 vegvisningsskilt | 23 |
| 800 underskilt | 10 (6 permanent + 4 trial-only 840.x) |
| 900 markeringsskilt | 1 |
| **Total** | **68** |

| Relevance | Missing |
|---|---|
| high | 8 |
| medium | 18 |
| low | 42 |

### Top 10 to add first
1. 306.0 Forbudt for alle kjøretøy
2. 306.1 Forbudt for motorvogn med unntak av liten elektrisk motorvogn
3. 306.6 Forbudt for syklende og fører av liten elektrisk motorvogn
4. 802 Avstand (underskilt)
5. 804 Utstrekning (underskilt)
6. 512 Holdeplass for buss
7. 524 Møteplass
8. 556.1 Automatisk trafikkontroll – punktmåling
9. 306.7 Forbudt for gående (and the rest of 306.x: 306.4, 306.5, 306.8, 306.10)
10. 408 Påbudt kjøreretning i rundkjøring

Other variants worth having but not counted above (low): 364 with 80 (Commons has 364.80); yellow temporary versions of fareskilt, e.g. 106.1-FYG and 110-FYG.

## DB records that look wrong or outdated

| DB id | DB name | Issue | Suggested fix |
|---|---|---|---|
| 379_0 | Slutt på sone med parkeringsforbud for små elektriske kjøretøy | Uses the 2021 wording, renamed in 2022 | «Slutt på sone med parkeringsforbud for liten elektrisk motorvogn» |
| 723_13 | Vegnummer for stamveg som ikke er europaveg | "stamveg" is an obsolete term. The regulation names 723.13–14 «Vegnummer for riksveg som ikke er europaveg» | Rename (723_13 and 723_14 are the same sign group) |
| 610_0 | Bensinstasjon | There is no "Bensinstasjon" in the regulation. 610 is «Drivstoff» (610.1 Drivstoff, 610.2 example). Probably a duplicate of 610_1 | Merge into 610_1 or rename to «Drivstoff» |
| 560_2 | Forbudt for gående og syklende på motorveg og motortrafikkveg | 560 is the generic «Opplysningstavle», and its sub-numbers are examples. Commons describes 560.2 as «Forvarsling om fartsmåling», which does not match our name | Check the image against the name and recategorise as a 560 example |
| 146_0 | Dyr | The regulation has only 146.1–146.5, so there is no 146.0. Likely a duplicate | Remove or merge |
| 146_1, 146_2, 146_5 | Dyr | Names do not say which animal (146.1 = elg; 146.3 = hjort and 146.4 = ku are already correct) | Add the animal to the name, checked against the image |
| 723_64 | Vegruteskilt | 723.61–66 are all «Andre omkjøringsruter». «Vegruteskilt» is the name of the whole 723 group | Rename to «Andre omkjøringsruter» |
| 831_0 | Parkeringsskive | Official title is «Parkeringsskive/gratisbillett» | Rename |
| 570_1H/1V | Nødutgangskilt for tunnel | Spelling: the official form is «Nødutgangsskilt for tunnel». 570.1 alone = «Nødutgang» | Fix spelling |
| 930_0 | Sperremarkering | Not in skiltforskriften. It exists only in N300 (part 2) | Keep, but mark as N300-only and not exam-relevant |
| 106_1 / 106_3 | Smalere veg | Two records have the same name. 106.1 = narrowing on both sides, 106.3 = on the left side | Make the names distinct |
| 908_0 | Hindermarkering – høydemarkering | The regulation title is just «Hindermarkering» | Optional rename |
| 902_OH … 906_OVH | (typo O vs 0) | Already known and left as is | — |
