# Data provenance and upstream terms

This graph combines source assertions while retaining separate source UIDs,
relationship contracts and provenance. It is not released under a new blanket
license that supersedes the upstream sources. The MIT license in `LICENSE`
applies to the interface code only.

The v1.8.0-hierarchy-review candidate adds source-backed professional middle
classes and typed connections while retaining prior independent source records.
The frozen input archive contains factual/derived records, attribution and
checksums; downloaded manufacturer pages and images are not release assets.
Wikipedia-derived definitions retain CC BY-SA 4.0 attribution and article URLs.

| Source | Upstream information |
|---|---|
| WordNet 3.1 | https://wordnet.princeton.edu/license-and-commercial-use |
| Wikidata | https://www.wikidata.org/wiki/Wikidata:Licensing |
| Wikipedia | https://en.wikipedia.org/wiki/Wikipedia:Copyrights |
| Open Tree of Life | https://tree.opentreeoflife.org/about/open-tree-of-life |
| World Flora Online | https://www.worldfloraonline.org/ |
| AviList | https://www.avilist.org/ |
| Catalogue of Life | https://www.catalogueoflife.org/ |
| FAA aircraft registry | https://registry.faa.gov/aircraftinquiry/ |
| EPA vehicle data | https://www.fueleconomy.gov/feg/download.shtml |
| NHTSA vPIC | https://vpic.nhtsa.dot.gov/ |
| Getty AAT | https://www.getty.edu/research/tools/vocabularies/aat/ |
| FoodOn | https://foodon.org/ |
| MIMO | https://mimo-international.com/ |
| NLM MeSH | https://www.nlm.nih.gov/databases/download/mesh.html |

The recorded source inventories identify Getty AAT as ODC-By 1.0 and FoodOn as
CC BY 4.0; other upstream terms and source/version-specific conditions should
be checked at the linked official sources. Preserve source attribution and
provenance when redistributing derived records. Some source-dependent text or
records may have conditions distinct from their source identifiers.

The latest graph also retains reference claims from RP Photonics, USDA, EIA,
FSA and other authoritative pages. Source references/URLs and evidence are
stored with the relevant relationships. They do not grant blanket rights to
those source publications. Historical MeSH and MIMO relations judged unsuitable
for classification are retained in the archive but quarantined in the API.

## Natural geography, mineral and weather catalogs

GeoNames is credited as the provider of selected natural-feature records and country/territory metadata, under [CC BY 4.0](https://www.geonames.org/about.html). WGS84 coordinates, native IDs and row hashes preserve attribution. The imported scope is 64 selected natural feature codes, not the entire GeoNames gazetteer. [Dump and field documentation](https://download.geonames.org/export/dump/readme.txt).

IMA-CNMNC's [September 2026 mineral master list](https://cnmnc.units.it/files/editor/IMA_Master_List_(2026-09).pdf) credits the International Mineralogical Association's Commission on New Minerals, Nomenclature and Classification. The catalog declares **CC BY-SA 3.0**; imported mineral facts, formulae, statuses, row/page references and derived catalog records retain that attribution and share-alike terms. Questionable species retain their native status and are not admitted as verified mineral types. The source PDF checksum is `2257c653491b346669ee5d38c98226a2bddbec0562a3675043730a01ca146973`.

The ten cloud genera use [WMO classification](https://public.wmo.int/world-meteorological-day-2017/classifying-clouds) and [NOAA definitions](https://www.weather.gov/lmk/cloud_classification). Names and source references are included; photographs are not redistributed.

## Manufacturer facts

Apple model-identification support: [iPhone](https://support.apple.com/en-us/108044), [MacBook Pro](https://support.apple.com/en-us/108052), [MacBook Air](https://support.apple.com/en-us/102869), [iPad](https://support.apple.com/en-us/108043), [Apple Watch](https://support.apple.com/en-us/108056), [AirPods](https://support.apple.com/en-us/109525).

[Canon Camera Museum cameras](https://global.canon/en/c-museum/camera.html) and [lenses](https://global.canon/en/c-museum/lens.html), [NVIDIA GeForce comparison](https://www.nvidia.com/en-us/geforce/graphics-cards/compare/), and [Samsung SSD warranty/product lines](https://semiconductor.samsung.com/consumer-storage/support/warranty/) provide native product designations, catalog identifiers and factual parameters. Preserve product URLs and publisher attribution. These records do not include manufacturer images or complete product-page prose, and do not grant rights to trademarks, images or source publications.

## Native task vocabularies

Dataset label catalogs reference their original publishers and the frozen vocabulary files in `dataset_catalogs`, including [Food-101](https://data.vision.ee.ethz.ch/cvl/datasets_extra/food-101/), [DTD](https://www.robots.ox.ac.uk/~vgg/data/dtd/), [Caltech-101](https://www.vision.caltech.edu/datasets/caltech101/), [SUN397](https://vision.princeton.edu/projects/2010/SUN/), [Places365](https://github.com/CSAILVision/places365), [EuroSAT](https://github.com/phelber/EuroSAT) and [NWPU-RESISC45](https://www.escience.cn/people/JunweiHan/NWPU-RESISC45.html). Some publisher vocabularies are distributed through [TensorFlow Datasets](https://github.com/tensorflow/datasets); the recorded source URL and hash identify the exact imported vocabulary. This database redistributes label metadata and reviewed type mappings, not image datasets. Dataset image licenses and access requirements remain those of their publishers.

## Habitat and physical type classifications

The European Environment Agency is credited for [EUNIS habitat classification](https://www.eea.europa.eu/en/datahub/datahubitem-view/638330ea-90e6-4e41-81ea-e70f25ae7117). The imported 2012 classification has 5,284 records and the 2021 classification has 3,860 records. Version and native code form distinct UIDs; levels and source references are retained. Follow the [EEA reuse policy](https://www.eea.europa.eu/en/legal-notice). These are ecological habitat types, rather than an assertion that every named physical feature has identical habitat scope.

USGS and the US National Park Service are credited for 21 additional physical types: [water glossary](https://water.usgs.gov/water-basics_glossary.html), [lake types](https://www.usgs.gov/special-topics/water-science-school/science/lakes-and-reservoirs), and [NPS mountain classifications](https://home.nps.gov/articles/rockies.htm). Per-record primary URLs and evidence are stored in the database. Images are not redistributed.

The mineral composition hierarchy uses the IMA source formula to express chemical-element content. Its 92 groupings do not infer crystal structure and are not a Dana or Strunz classification. The 96 IMA questionable-status entries remain source records without classification admission.

Imported eunis2012.xls SHA-256: `cde7b23f1b91c0167f3b93c72938acb6cd8a22becd0d785fcbf0d9278a0021f5`.

Imported eunis2021.xlsx SHA-256: `1427d22db8d77d1053ab1683aa60713bdec3d810605dd6b7bc16683b4ca14665`.

## Additional primary catalog attribution

Vishay diode and multilayer ceramic capacitor catalogs: [vishay-diodes](https://www.vishay.com/en/diodes/), [vishay-ceramic-smd](https://www.vishay.com/en/capacitors/ceramic/surface-mount/).

Intel processor specifications: [intel-core-ark](https://www.intel.com/content/www/us/en/ark/products/series/122139/intel-core-processors.html), [intel-ultra-ark](https://www.intel.com/content/www/us/en/ark/products/series/236800/intel-core-ultra-processors.html).

NVIDIA CUDA GPU tables: [nvidia-gpus](https://developer.nvidia.com/cuda-gpus), [nvidia-legacy-gpus](https://developer.nvidia.com/cuda-legacy-gpus).

TP-Link network devices: [tplink-routers](https://www.tp-link.com/us/home-networking/wifi-router/), [tplink-switches](https://www.tp-link.com/us/business-networking/omada-switch-unmanaged/).

Dell displays and desktop computers: [dell-monitors](https://www.dell.com/en-us/shop/monitors/ar/8605), [dell-desktops](https://www.dell.com/en-us/shop/desktop-computers/scr/desktops).

Samsung TVs, SSDs and earbuds: [samsung-tv](https://www.samsung.com/us/televisions-home-theater/tvs/all-tvs/), [samsung-ssd](https://semiconductor.samsung.com/consumer-storage/internal-ssd/), [samsung-earbuds-alt](https://www.samsung.com/us/audio-sound/galaxy-buds/).

Epson printer catalog: [epson-printers](https://epson.com/For-Home/Printers/c/h1).

NSIDC glacier types: [nsidc-glacier-science](https://nsidc.org/learn/parts-cryosphere/glaciers/science-glaciers).

USGS volcano, desert and aquifer types: [usgs-volcanoes](https://pubs.usgs.gov/gip/volc/types.html), [usgs-deserts](https://pubs.usgs.gov/gip/deserts/types/), [usgs-aquifers](https://www.usgs.gov/special-topics/water-science-school/science/aquifers-and-groundwater).

NPS waterfall types: [nps-waterfalls](https://www.nps.gov/iafl/learn/kidsyouth/upload/IAFL-Jr-Ranger-11-2022-compressed-508.pdf).

NOAA CMECS coastal classification: [noaa-cmecs](https://repository.library.noaa.gov/view/noaa/41982/noaa_41982_DS1.pdf).

Native identifiers, factual model designations, relation types, source URLs and evidence remain attached to the imported records. Manufacturer names and trademarks remain their owners’ property. Catalog facts do not grant rights to photographs or complete source publications.

## Review candidate catalog scope

The v1.7.1-review candidate additionally retains 3,885 factual series/part records from Murata's C02E-16 multilayer ceramic capacitor catalogue: 12 series and 3,873 orderable part configurations. The [catalogue copy](https://dsvr.org/kompo/datasheets/GRM155F51A334ZE01D.pdf) is referenced with its retained source hash and publisher attribution; the original publication and product images are not distributed as release assets.

[Garmin's product catalogue](https://www.garmin.com.sg/products/wearables/) contributes 60 model/configuration facts; the [Fitbit Charge 6 announcement](https://blog.google/products-and-platforms/devices/fitbit/fitness-tracker-charge-6/) contributes one product design. Counts include SKU variants and do not mean 61 distinct model families or complete brand coverage. Publisher copyright, trademarks and source URLs remain attached to the factual identifiers.

[openFDA device classification](https://open.fda.gov/apis/device/classification/) supplies 7,094 regulatory type records, including 935 independently grounded physical type records. [openFDA UDI](https://open.fda.gov/apis/device/udi/) contributes 705 explicit manufacturer model identifiers and 260,296 sized catalog configurations from the frozen 52-partition input. The [openFDA license](https://open.fda.gov/license/) is CC0. GMDN fields are excluded from the derived records. Ambiguous version/model values remain outside model admission. Device identifiers describe catalog/packaging definitions, not serialized physical instances; regulatory assignment is preserved as `REGULATED_AS`.

## Professional middle classifications

[FAA aircraft reference documentation](https://registry.faa.gov/database/ardata.pdf)
defines native aircraft, engine and engine-count codes. The candidate classifies
94,043 retained model reference records using those fields. Structure and
propulsion are independent dimensions; hybrid/other codes do not imply a
conventional airframe, intended use or a serialized aircraft identity.

[Environment Ontology](https://github.com/EnvironmentOntology/envo) contributes
173 native environmental-feature classes under CC0 1.0. Retained native `is_a`
relations support their hierarchy; part-of relations and logical restrictions
are not converted to subclass claims. Existing biological and EUNIS versions
retain their own native classifications.

Professional hardware definitions reference [Microsoft form factors](https://learn.microsoft.com/en-us/windows-hardware/design/form-factors/form-factors),
[Intel graphics types](https://www.intel.com/content/www/us/en/support/articles/000057824/graphics.html),
[EIZO LCD technologies](https://www.eizo.com/library/management/cms/02.html/),
[TP-Link switch categories](https://www.tp-link.com/us/document/12901/),
[Samsung SSD types](https://semiconductor.samsung.com/news-events/tech-blog/your-guide-to-samsungs-wide-ranging-ssd-selection/),
[John Deere tractor forms](https://www.deere.com.au/en/tractors/) and
[Nintendo Switch operating forms](https://www.nintendo.com/en-ca/gaming-systems/switch/system/).
Each derived class records its definition, axis and primary reference; only
explicit native fields or retained definitions connect individual designs.

[Apple AirPods Pro specifications](https://www.apple.com/airpods-pro/specs/) and
[NVIDIA RTX 3090/3090 Ti specifications](https://www.nvidia.com/en-in/geforce/graphics-cards/30-series/rtx-3090-3090ti/)
support exact product-type connections, rather than propagation to every
product in a brand or family. Publisher copyright and trademarks remain with
their owners.

EPA fuel and hybrid fields classify individual configurations. Four retained
EPA car-line groups use the [historical native classification rule](https://www.govinfo.gov/content/pkg/CFR-2014-title40-vol30/pdf/CFR-2014-title40-vol30-sec600-315-08.pdf)
as regulatory navigation; car-line majority rules are not physical claims
about every configuration's body or seat count. [USGS aquifer definitions](https://pubs.usgs.gov/ha/ha730/ch_h/H-text2.html)
support unconsolidated/alluvial types; named, located aquifers retain INSTANCE
roles. Per-record source URLs, native-row hashes and scope evidence are retained.

The [Vertebrate Breed Ontology](https://github.com/monarch-initiative/vertebrate-breed-ontology) contributes 40,223 native ontology facts, including its classification framework, under CC BY 4.0. This count is not a count of dog breeds. Native identifiers and source-declared navigation remain distinct from strict inclusion and task-label identity.
