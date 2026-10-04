"""Run after installing the package and downloading the database."""
from fineatlas import FineAtlas

with FineAtlas('.') as graph:
    print(graph.stats())
    print(graph.domain('minerals'))
    print(graph.domain_children('forests'))
    print(graph.exact('laser diode'))
    print(graph.neighbors('wikidata:Q321098', direction='parents'))
    print([node['label'] for node in graph.path('wikidata:Q321098')])
