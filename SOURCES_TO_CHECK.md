# Fuentes por revisar

Fuentes propuestas el 9 de noviembre de 2026, con una primera valoración. Nada de esto está hecho todavía,
salvo lo marcado como "ya cubierta". Antes de añadir una fuente hay que comprobar sus condiciones de uso
(que permitan descargar con programas) y si tiene API, OAI-PMH o un catálogo descargable.

Valoración:
- **Prioridad**: lo que más rendiría.
- **Quizá**: depende de qué autores se sigan.
- **Ya cubierta**: llega por otra fuente que ya usamos.
- **No sirve**: no son obras de un autor que se puedan subir a Calibre, son de pago, o sus condiciones lo prohíben.

Las direcciones con (?) estaban cortadas en la lista original y están completadas de memoria: comprobarlas.

## Lo primero

1. **Abrir la página del artículo que da OpenAlex** (`landing_page_url` de las copias en abierto), no solo
   su enlace directo al PDF. El descargador ya sabe sacar el PDF de esas páginas (`citation_pdf_url`).
   Cubriría las revistas en OJS de esta lista (Complutenses, RACO, CSIC, Open Library of Humanities,
   Janeway, OpenEdition Journals, Heidelberg) sin fuentes nuevas ni gasto de OpenAlex.
2. **Clave de CORE** (`CORE_API_KEY` en `.env`, gratis en core.ac.uk/services/api): el buscador ya existe.
   Daría repositorios universitarios y tesis (TDX, HAL, parte de DART-Europe, OATD y Humanities Commons).

## Agregadores y directorios de humanidades

| Fuente | Dirección | Valoración |
|---|---|---|
| Humanities Commons (MLA) | hcommons.org | Quizá: buena parte llega por CORE y por los DOI de DataCite en OpenAlex; tiene API (InvenioRDM) |
| MLA CORE / KC Works | works.hcommons.org | Igual que la anterior |
| PhilPapers | philpapers.org | No sirve: sus condiciones prohíben descargar con programas sin permiso escrito |
| PhilArchive | philarchive.org | Ya cubierta (catálogo local por OAI-PMH) |
| Isidore | isidore.science | Quizá: buscador francés con API y SPARQL; reúne HAL, OpenEdition y Persée. Para autores franceses |
| Recensio.net | recensio.net | No sirve: reseñas, casi todas en HTML |
| Perlego, Academia.edu | — | Descartadas en la lista original (de pago / sin control de derechos) |

## Revistas y plataformas de acceso abierto

| Fuente | Dirección | Valoración |
|---|---|---|
| Open Library of Humanities | openlibhums.org | Prioridad, con el punto 1 (tienen DOI, están en OpenAlex) |
| OpenEdition Journals y Books | openedition.org | Journals: punto 1; Books: ya cubierta (DOAB). Parte es freemium: no todo el PDF es abierto |
| Project MUSE (abierto) | muse.jhu.edu | No sirve directamente: condiciones contra los programas; sus libros abiertos llegan por OAPEN |
| Janeway / revistas de Birkbeck | openlibhums.org | Prioridad, con el punto 1 |
| Digital Humanities Quarterly | digitalhumanities.org/dhq | No sirve: artículos en HTML |
| Bryn Mawr Classical Review | bmcr.brynmawr.edu | No sirve: reseñas en HTML |
| Revistas Científicas Complutenses | revistas.ucm.es | Prioridad, con el punto 1 (OJS, DOI, también en Dialnet) |
| RACO | raco.cat | Prioridad, con el punto 1 (OJS, tiene OAI-PMH) |
| Revistas del CSIC | revistas.csic.es | Prioridad, con el punto 1 (OJS, DOI) |
| Biblioteca Saavedra Fajardo | saavedrafajardo.org | No sirve: pequeña y en HTML |

## Libros académicos abiertos

| Fuente | Dirección | Valoración |
|---|---|---|
| Open Book Publishers | openbookpublishers.com | Ya cubierta (DOAB/OAPEN, OpenAlex) |
| punctum books | punctumbooks.com | Ya cubierta (DOAB/OAPEN) |
| Language Science Press | langsci-press.org | Ya cubierta (DOAB/OAPEN) |
| Ubiquity Press | ubiquitypress.com | Ya cubierta (DOAB, OpenAlex) |
| UCL Press | uclpress.co.uk | Ya cubierta (DOAB/OAPEN) |
| Luminos (University of California Press) | luminosoa.org | Ya cubierta (DOAB/OAPEN) |
| Knowledge Unlatched | knowledgeunlatched.org | Ya cubierta (OAPEN) |
| UNE, editoriales universitarias (Universidad de Sevilla...) | unebook.es | No sirve: casi todo es de pago |
| Fondo Editorial PUCP, Ediciones UNAM | (colecciones abiertas) | Quizá: en parte ya llegan por DOAB; mirar si tienen OAI-PMH (UNAM usa OMP) |

## Fuentes primarias, manuscritos y archivos

| Fuente | Dirección | Valoración |
|---|---|---|
| PARES | pares.cultura.gob.es (?) | No sirve: documentos de archivo en imagen |
| Biblioteca Digital Hispánica (BNE) | bnedigital.bne.es | Ya cubierta (ver PENDIENTES.md) |
| Biblioteca Virtual Miguel de Cervantes | cervantesvirtual.com (?) | Ya cubierta (ver PENDIENTES.md) |
| Biblioteca Virtual de Prensa Histórica | prensahistorica.mcu.es | No sirve: periódicos en imagen |
| Hispana | hispana.mcu.es (?) | Ya cubierta, creo: envía sus colecciones a Europeana. Comprobar |
| Memoria Digital de Catalunya | mdc.csuc.cat | Ya cubierta, creo, por Europeana. Comprobar |
| Galiciana | biblioteca.galiciana.gal (?) | Ya cubierta, creo, por Europeana. Comprobar |
| Biblioteca Digital Real Academia de la Historia | bibliotecadigital.rah.es | No sirve, salvo libros antiguos sueltos: sobre todo fondos de archivo |
| e-codices | e-codices.ch | No sirve: manuscritos en imagen |
| Digital Bodleian | digital.bodleian.ox.ac.uk | No sirve: manuscritos en imagen |
| British Library Digitised Manuscripts | bl.uk/manuscripts | No sirve: manuscritos en imagen |
| DigiVatLib | digi.vatlib.it | No sirve: manuscritos en imagen |
| Gallica | gallica.bnf.fr | Ya cubierta |
| Münchener DigitalisierungsZentrum (MDZ) | digitale-sammlungen.de | Quizá: libros antiguos en PDF, con API; creo que también llega por Europeana |
| Deutsche Digitale Bibliothek | deutsche-digitale-bibliothek.de | Quizá: API con clave; en parte por Europeana |
| Polona | polona.pl | Quizá: en parte por Europeana |
| Europeana | europeana.eu | Ya cubierta (con `EUROPEANA_API_KEY`) |
| Library of Congress Digital Collections | loc.gov/collections | Quizá: API JSON; libros antiguos en inglés de dominio público |
| World Digital Library | (en loc.gov) | Igual que Library of Congress |
| Digital Public Library of America | dp.la | Quizá: API con clave; reúne bibliotecas de EE. UU. y enlaza a ellas |
| HathiTrust | hathitrust.org | Ya cubierta |
| Internet Archive | archive.org | Ya cubierta (sus obras pasan por revisión: reviews.py) |

## Clásicos, filología y textos antiguos

| Fuente | Dirección | Valoración |
|---|---|---|
| Perseus Digital Library | perseus.tufts.edu (?) | No sirve tal cual: textos en TEI/HTML. Se podrían convertir a EPUB (proyecto aparte) |
| Scaife Viewer | scaife.perseus.org | Igual que Perseus |
| The Latin Library | thelatinlibrary.com | Igual que Perseus (HTML) |
| Corpus Corporum (Zúrich) | mlat.uzh.ch (?) | Igual que Perseus |
| Open Greek and Latin | opengreekandlatin.org | Igual que Perseus (TEI en GitHub) |
| Papyri.info | papyri.info | No sirve: papiros documentales |
| Corpus del Nuevo Diccionario Histórico (RAE) | rae.es | No sirve: solo consulta |
| CORDE y CREA | corpus.rae.es | No sirve: solo consulta |
| Sacred Texts | sacred-texts.com | No sirve: HTML; muchos están ya en Gutenberg o Wikisource |
| Chinese Text Project | ctext.org | No sirve: consulta en HTML |
| Al-Maktaba al-Shamila | shamela.ws (?) | No sirve: formato propio |

## Historia del arte, arqueología y música

| Fuente | Dirección | Valoración |
|---|---|---|
| Getty Publications Virtual Library | getty.edu/publications/virtuallibrary | No hace falta automatizar: unos cientos de libros en PDF, mejor a mano |
| MetPublications | metmuseum.org/met-publications (?) | Igual que Getty |
| Smithsonian Open Access | si.edu/openaccess | No sirve: imágenes y datos |
| Rijksmuseum Research Library | rijksmuseum.nl | No sirve: imágenes y catálogo |
| arthistoricum.net | arthistoricum.net | Quizá: sus libros abiertos (heiBOOKS) probablemente ya llegan por DOAB; comprobar |
| Heidelberg Historic Literature | digi.ub.uni-heidelberg.de | Quizá: revistas de arte antiguas digitalizadas; las actuales, con el punto 1 |
| Open Context | opencontext.org | No sirve: datos de arqueología |
| tDAR | tdar.org | No sirve: datos de arqueología |
| IMSLP | imslp.org | No sirve: partituras |
| RILM Abstracts, RIPM | — | Descartadas en la lista original (de pago) |

## Filosofía y enciclopedias académicas

| Fuente | Dirección | Valoración |
|---|---|---|
| Stanford Encyclopedia of Philosophy | plato.stanford.edu | No sirve: entradas en HTML; el PDF es para socios de pago |
| Internet Encyclopedia of Philosophy | iep.utm.edu | No sirve: entradas en HTML |
| Diccionario Biográfico Español (RAH) | dbe.rah.es | No sirve: biografías en HTML |

## Tesis doctorales

| Fuente | Dirección | Valoración |
|---|---|---|
| TDX | tdx.cat | Prioridad, con la clave de CORE (punto 2); también tiene OAI-PMH |
| TESEO | educacion.gob.es/teseo | No sirve: solo la ficha de la tesis, sin archivo |
| DART-Europe | dart-europe.org | Quizá: enlaza a repositorios que ya reúne CORE |
| OATD | oatd.org | Quizá: igual que DART-Europe |
| theses.fr | theses.fr | Quizá: tiene API; los archivos suelen estar en HAL (llega por CORE) |
| BDTD | bdtd.ibict.br | Quizá: OAI-PMH; solo si se siguen autores brasileños |
