# Fonts embedded in the paper and figures

`pdffonts` identifies embedded subsets of Nimbus Roman No9 L, Latin Modern
Mono, Computer Modern and DejaVu Sans in the compiled PDF. The figures use
DejaVu Sans. No standalone font binaries are distributed here.

The following notices are copied from the installed fonts used for this build:

- [Nimbus Roman notices](font-notices/NIMBUS-ROMAN-NOTICES.txt): exact readable
  headers of the three URW Type 1 files used by pdfTeX. They retain the 1999
  URW copyright and explicit PostScript/PDF document-embedding exception.
  A [GNU GPL version 2 text](font-notices/GNU-GPL-2.txt) accompanies them.
- [Computer Modern notices](font-notices/COMPUTER-MODERN-NOTICES.txt): exact
  copyright, reserved-name and license headers from all 13 embedded AMS font
  inputs. The referenced [SIL Open Font License 1.1](font-notices/SIL-OFL-1.1.txt)
  text is included.
- Latin Modern: the existing [GUST Font License](GUST-FONT-LICENSE.txt),
  upstream [README](font-notices/README-Latin-Modern.txt),
  [manifest](font-notices/MANIFEST-Latin-Modern.txt) and installed distribution's
  [copyright and license text](font-notices/Latin-Modern-Debian-copyright.txt).
- [DejaVu license](font-notices/DEJAVU-LICENSE.txt): the complete notice shipped
  beside the matplotlib font files used by the figure generator.

These notices apply to their respective font inputs. The repository software
license does not replace them. SVG figures name DejaVu Sans as a font family
and contain no embedded font binary; browsers can use an available fallback.
