"""Run after installing the package and downloading the complete graph."""
from fineatlas import FineAtlas

with FineAtlas('.') as graph:
    print(graph.stats())
    print(graph.exact('laser diode'))
    print(graph.neighbors('wikidata:Q321098', direction='parents'))
    print([node['label'] for node in graph.path('wikidata:Q321098')])
