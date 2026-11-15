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

---

# Listas segunda y tercera (15 de noviembre de 2026)

Unas 390 fuentes más. Las marcadas "comprobada" se probaron desde este PC el 15 de noviembre (pocas peticiones
por sitio); el resto está sin comprobar. Se agrupan las que reciben la misma valoración.

## Siguientes candidatas

1. **Wikimedia Commons** (comprobada): `https://commons.wikimedia.org/w/api.php?action=query&generator=search&gsrnamespace=6&gsrsearch=<autor> filetype:pdf&prop=imageinfo&iiprop=url|mime|size`.
   Libros escaneados en PDF y DjVu, descarga directa desde `upload.wikimedia.org`, sin Cloudflare. Con "Fichte" da
   PDF y DjVu de sus obras. Entraría como `BookSource` (búsqueda por autor y título), con el mismo User-Agent y
   ritmo que Wikisource. Calibre guarda DjVu, aunque su visor no lo abre.
2. **Biblioteca Virtual de Polígrafos (Fundación Ignacio Larramendi)** (comprobada): OAI-PMH en
   `https://www.larramendi.es/i18n/oai/oai.cmd` (oai_dc con `dc:creator`, 16.614 registros; conjuntos
   "Set para objetos digitales", "Clásicos Tavera"...). Pensamiento español (Menéndez Pelayo, Gaos, Méndez Bejarano...).
   Entraría como copia local por OAI-PMH, igual que Dialnet. Falta comprobar qué registros tienen PDF: el registro 626
   solo ofrecía la ficha.
3. **Darwin Online** (comprobada): PDFs directos en `https://darwin-online.org.uk/converted/pdf/...`, enlazados desde
   `contents.html`. El servidor es Cloudflare, pero no pide verificación. Solo sirve para Darwin, que es un autor
   seguido: una fuente pequeña que lea `contents.html`, o una descarga única a mano.
4. **MDZ, Biblioteca Estatal de Baviera** (ya en la primera lista; comprobada en parte): `robots.txt` lo permite todo
   y la API IIIF funciona (`https://api.digitale-sammlungen.de/iiif/presentation/v2/<bsbid>/manifest`). No se ha
   encontrado una API de búsqueda ni la URL del PDF (`/pdf/<bsbid>` da 404). La BSB envía a Europeana, y muchos de sus
   libros están en Internet Archive (copias de Google, `bub_gb_...`). Probarla primero por Europeana.
5. **e-rara, impresos antiguos suizos** (comprobada): OAI-PMH en `https://www.e-rara.ch/oai` (mets, mods, oai_dc).
   **Pero su `robots.txt` prohíbe todo a los programas** que no sean buscadores. Pedir permiso a
   issue-erara@library.ethz.ch; mientras tanto, por Europeana.
6. **The Online Books Page** (comprobada): `https://onlinebooks.library.upenn.edu/webbin/book/search?author=<autor>&amode=words`,
   con `Crawl-delay: 5`. **Rinde poco**: de 179 enlaces para Fichte, 177 llevan a HathiTrust. Solo valdría si se
   resuelve HathiTrust.

## Índices de repositorios y de libros gratuitos

| Fuente | Dirección | Valoración |
|---|---|---|
| OpenDOAR, ROAR | v2.sherpa.ac.uk/opendoar, roar.eprints.org | No sirve como fuente: es un directorio. Útil para encontrar el OAI-PMH de otros repositorios |
| The Online Books Page | onlinebooks.library.upenn.edu (comprobada) | Quizá: casi todo lleva a HathiTrust (ver "Siguientes candidatas") |
| Digital Commons Network | network.bepress.com | Ya cubierta: sus repositorios llegan por CORE y OpenAlex |
| RedIB, Biblat | redib.org, biblat.unam.mx | Ya cubierta: son índices; las revistas con DOI llegan por OpenAlex y el punto 1 |
| RCAAP (Portugal) | rcaap.pt | Ya cubierta por CORE y OpenAlex; OAI-PMH propio solo si se siguen autores portugueses |
| Universal Short Title Catalogue | ustc.ac.uk | No sirve: catálogo; sus enlaces llevan a MDZ, Google Books, etc. |
| Getty Research Portal | portal.getty.edu | Ya cubierta en parte: enlaza sobre todo a Internet Archive y HathiTrust |
| Open Textbook Library, Pressbooks Directory | open.umn.edu/opentextbooks, pressbooks.directory | No sirve: manuales universitarios |

## Revistas

| Fuente | Dirección | Valoración |
|---|---|---|
| Revistas universitarias españolas: Alcalá, Alicante, Cádiz, Castilla-La Mancha, Córdoba, Jaume I, León, Málaga, Santiago, UPV/EHU, Valladolid | ojs.uah.es, revistes.ua.es, revistas.uca.es, revista.uclm.es, uco.es/ucopress/ojs, e-revistes.uji.es, revpubli.unileon.es, revistas.uma.es, revistas.usc.gal, ojs.ehu.eus, revistas.uva.es | Prioridad, con el punto 1: son OJS con DOI, están en OpenAlex y en Dialnet |
| Revistas latinoamericanas, italianas y nórdicas: Filo UBA, Memoria Académica UNLP, PUCP, U. Nacional de Colombia, U. de Antioquia, U. de Costa Rica, USP, El Colegio de México, Firenze University Press, Edizioni Ca' Foscari, AMS Acta, heiJOURNALS, Journal.fi, Septentrio, Idunn | (ver lista) | Ya cubierta: OpenAlex con el punto 1, y CORE para los repositorios |
| Plataformas nacionales: AJOL, DergiPark, CyberLeninka, KCI, Garuda, ASJP, Hrčak | ajol.info, dergipark.org.tr, cyberleninka.ru, kci.go.kr, garuda.kemdikbud.go.id, asjp.cerist.dz, hrcak.srce.hr | Quizá: solo si se siguen autores de esos países; casi todas están en OpenAlex |
| Internet Archaeology | intarch.ac.uk | No sirve: artículos en HTML |
| e-periodica (revistas suizas) | e-periodica.ch | Quizá: revistas antiguas digitalizadas; `/oai/` da 404 (comprobada), buscar otra vía |
| DigiZeitschriften (parte abierta) | digizeitschriften.de | Quizá: revistas alemanas antiguas; sin API conocida (sin comprobar) |
| Prensa: e-newspaperarchives.ch, Welsh Newspapers, Hemeroteca de Lisboa, Periodika, Anáforas, AHIRA, California Digital Newspaper Collection, Papers Past, hemerotecas de ABC y La Vanguardia | (ver lista) | No sirve: prensa en imagen |

## Editoriales con libros abiertos

| Fuente | Dirección | Valoración |
|---|---|---|
| transcript, Universitätsverlag Göttingen, Stockholm UP, Helsinki UP, Westminster, Mattering, African Minds, Athabasca, Calgary, Cornell Open, Firenze UP, Casa de Velázquez, Archaeopress (abiertos) | (ver lista) | Ya cubierta: están en DOAB/OAPEN (Casa de Velázquez, por OpenEdition Books) |
| Editorial CSIC, Editorial Universidad de Sevilla, Libros UNAM, El Colegio de México, EDULP, Publicaciones Filo UBA | editorial.csic.es, editorial.us.es, libros.unam.mx, libros.colmex.mx, libros.unlp.edu.ar, publicaciones.filo.uba.ar | Quizá: comprobar si están en DOAB; si no, OMP/OAI-PMH propio (sin comprobar) |
| Fundación Ignacio Larramendi | larramendi.es (OAI comprobado) | Prioridad: ver "Siguientes candidatas" |
| Biblioteca Ayacucho | bibliotecayacucho.gob.ve | Quizá: PDFs sueltos sin API; mejor a mano |
| Edition Open Sources / Access (Max Planck) | edition-open-sources.org | Quizá: pocos títulos; la página de publicaciones no enlaza PDFs directos (comprobada); a mano |
| Sidestone Press | sidestone.com | No sirve: lectura en línea; el PDF es de pago |
| Smarthistory | smarthistory.org | No sirve: HTML |

## Tesis

| Fuente | Dirección | Valoración |
|---|---|---|
| White Rose eTheses, AMS Dottorato, Shodhganga | etheses.whiterose.ac.uk, amsdottorato.unibo.it, shodhganga.inflibnet.ac.in | Ya cubierta: llegan por CORE (cuando tenga clave) |
| EBSCO Open Dissertations | biblioboard.com/opendissertations | Quizá: sin API conocida (sin comprobar) |

## Bibliotecas digitales de España

| Fuente | Dirección | Valoración |
|---|---|---|
| Real Biblioteca, BINADI, Asturias, La Rioja, Biblioteca Virtual Galega, Simurg (CSIC), Real Jardín Botánico, BIDICAM, Memoria de Madrid | (ver lista) | Ya cubierta, creo: la mayoría usa DIGIBIS con OAI-PMH y envía a Hispana y Europeana. Comprobar cuando funcione Europeana |
| Centro Virtual Cervantes (actas de la AIH) | cvc.cervantes.es | Quizá: actas en PDF, sin API; a mano o fuente por título |
| Biblioteca Virtual de la Filología Española | bvfe.es (comprobada: responde) | Quizá: catálogo que enlaza a copias de otras bibliotecas; solo para filología |
| BIDISO, ARTELOPE, EMOTHE, ALPI, Fichero general de la RAE, Lletra, BIESES, Fundación Joaquín Díaz, MANES, Centro de Documentación de las Artes Escénicas | (ver lista) | No sirve: bases de datos, consulta o HTML |
| Gazeta del BOE, Diarios de Sesiones del Congreso | boe.es, congreso.es | No sirve: boletines y debates |

## Latinoamérica

| Fuente | Dirección | Valoración |
|---|---|---|
| Domínio Público, Biblioteca Jurídica Virtual (UNAM), Históricas UNAM, Biblioteca Digital U. de Chile, Biblioteca Digital Luso-Brasileira, Senado de Brasil, U. Nacional de Cuyo, Bogotá, Banco de la República, BN Perú, BN Uruguay | (ver lista) | Quizá: solo si se siguen autores de esos países (Domínio Público y la Jurídica Virtual tienen muchos PDF) |
| CODESRIA | codesria.org | Ya cubierta en parte: libros en DOAB y OpenAlex |

## Europa

| Fuente | Dirección | Valoración |
|---|---|---|
| e-rara | e-rara.ch (OAI comprobado) | Quizá: tiene OAI-PMH, pero `robots.txt` lo prohíbe a los programas; pedir permiso |
| Bibliotecas con libros antiguos digitalizados: BVH (Tours), Numelyo, Herzog August Bibliothek, Staatsbibliothek Berlin, SLUB Dresden, GDZ Göttingen, ULB Halle, ONB, Leiden, National Library of Scotland, National Library of Wales, Trinity College Dublin, Manchester, Belgica (KBR), Biblioteca Real de Dinamarca, FBC (Polonia), MEK, dLib, DIGAR, ePaveldas, Anemi | (ver lista) | Quizá: casi todas envían a Europeana (las alemanas, también a la Deutsche Digitale Bibliothek). Mejor por Europeana que una a una; GDZ y SLUB tienen OAI-PMH (sin comprobar) |
| BIU Santé, Rosalis, Bibliothèque numérique de l'INHA | (ver lista) | Ya cubierta, creo: son socias de Gallica |
| Deutsches Textarchiv | deutschestextarchiv.de (comprobada: responde) | Quizá: textos alemanes 1600–1900 (Kant, Fichte, Hegel) en TEI y texto, sin PDF ni EPUB: convertir, proyecto aparte |
| e-manuscripta, Laurenziana, Museo Galileo, Irish Script on Screen, Bildindex, Regesta Imperii | (ver lista) | No sirve: manuscritos, imágenes o regestos |
| Nasjonalbiblioteket | nb.no | No sirve: mucho solo desde IP noruega y con derechos |
| Biblioteca Presidencial, NEB, FEB (Rusia) | prlib.ru, rusneb.ru, feb-web.ru | No sirve para estos autores; NEB tiene gran parte con derechos |

## Reino Unido, Irlanda y EE. UU.

| Fuente | Dirección | Valoración |
|---|---|---|
| Corpus of Middle English, Middle English Dictionary, Anglo-Norman Dictionary, Bosworth-Toller, London Lives, Connected Histories, Historic Hansard | (ver lista) | No sirve: corpus, diccionarios y consulta |
| Making of America, Evans-TCP, ECCO-TCP | quod.lib.umich.edu | Quizá: textos transcritos (TEI/HTML; los TCP están en GitHub). Convertir, proyecto aparte; Making of America también está en HathiTrust |
| NYPL, Harvard CURIOSity, Yale, Princeton, Newberry, Huntington, Folger, Walters, Watson Library, Smithsonian Libraries, Archives of American Art, Juilliard | (ver lista) | No sirve: sobre todo imágenes y manuscritos; sus libros impresos suelen estar en Internet Archive o HathiTrust |
| Canadiana, BAnQ, Calisphere, Portal to Texas History, Digital Library of Georgia, Digital Commonwealth, DocSouth, dLOC, DLME | (ver lista) | Quizá: regionales; solo si se siguen autores de allí. Las de EE. UU. las reúne DPLA (primera lista) |
| JSTOR Early Journal Content | archive.org/details/jstor_ejc | Ya cubierta: está en Internet Archive |
| Mark Twain Project, Willa Cather Archive, Papers of Abraham Lincoln, SlaveVoyages, Lantern | (ver lista) | No sirve: ediciones en HTML o datos |
| Wikimedia Commons | commons.wikimedia.org (API comprobada) | Prioridad: ver "Siguientes candidatas" |
| Endangered Archives Programme | eap.bl.uk | No sirve: archivos en imagen |

## Asia, Oriente Próximo y África

| Fuente | Dirección | Valoración |
|---|---|---|
| Fundación Hindawi, Aozora Bunko, Proyecto Ben Yehuda, Arabic Collections Online | hindawi.org/books, aozora.gr.jp, benyehuda.org, dlib.nyu.edu/aco | Quizá: dan EPUB o PDF, pero solo si se siguen autores en árabe, japonés o hebreo |
| South Asia Open Archives | jstor.org/site/saoa | No sirve: está en JSTOR, cuyas condiciones prohíben los programas |
| International Dunhuang Programme, Digital Silk Road, NIJL, Kotenseki, HebrewBooks, Ktiv, Ganjoor, Sanskrit Documents, Muktabodha, Rekhta, Kanripo, Shuge, Japan Search, Korean Classics DB, DISA | (ver lista) | No sirve para estos autores: manuscritos, imágenes o formatos propios |
| CDLI, ORACC, ETCSL, Thesaurus Linguae Aegyptiae | (ver lista) | No sirve: corpus de tablillas y papiros |

## Literatura, clásicas, ciencia y filosofía

| Fuente | Dirección | Valoración |
|---|---|---|
| Darwin Online | darwin-online.org.uk (PDF comprobados) | Prioridad para Darwin: ver "Siguientes candidatas" |
| Leibniz-Edition | leibniz-edition.de | Quizá: volúmenes de la Akademie-Ausgabe en PDF; pocos archivos muy grandes, mejor a mano |
| Project Gutenberg Australia | gutenberg.net.au | Quizá: cuidado, publica obras de dominio público en Australia que pueden tener derechos en España |
| ManyBooks | manybooks.net | Ya cubierta: reempaqueta Gutenberg |
| Newton Project, Wittgenstein Source, Hume Texts Online, ARTFL, Roman Law Library, MEGAdigital | (ver lista) | No sirve: transcripciones en HTML/TEI o facsímiles |
| Linda Hall Library | lindahall.org | Quizá: colecciones digitales sobre todo en imagen (sin comprobar) |
| Attalus, Livius, PHI Latin Texts, Digital Latin Library | (ver lista) | No sirve: HTML y consulta |
| Bartleby, Luminarium, Poetry Foundation, A Media Voz | (ver lista) | No sirve: HTML |

## Arte, mapas, música y lenguas

| Fuente | Dirección | Valoración |
|---|---|---|
| National Gallery of Art, Cleveland Museum of Art, David Rumsey, Old Maps Online, IGN | (ver lista) | No sirve: imágenes y mapas |
| Bach Digital, Beethoven-Haus, Digital Mozart Edition, Musopen, RISM | (ver lista) | No sirve: partituras, audio y catálogos |
| The Language Archive, AILLA | archive.mpi.nl, ailla.utexas.org | No sirve: grabaciones y datos lingüísticos |
