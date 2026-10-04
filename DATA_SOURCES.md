# Data provenance and upstream terms

This graph combines source assertions while retaining separate source UIDs,
relationship contracts and provenance. It is not released under a new blanket
license that supersedes the upstream sources. The MIT license in `LICENSE`
applies to the interface code only.

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
