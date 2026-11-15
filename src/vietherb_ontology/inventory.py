"""Read-only, provenance-aware inventory of an RDF/XML ontology.

The inventory deliberately performs no OWL reasoning and does not rewrite IRIs.
It is intended as a reproducible input to a later RDF-to-graph mapping design.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from rdflib import Graph, Literal, RDF, RDFS, OWL, URIRef
from .pipeline import parse_bytes
from rdflib import __version__ as rdflib_version


def load_graph(source: str | Path, *, format: str = "xml") -> Graph:
    """Parse *source* without inference or IRI normalization."""

    path = Path(source).resolve()
    return parse_bytes(path.read_bytes(), format=format, base=path.as_uri())


def _iri_values(graph: Graph, predicate: Any, object_: Any) -> list[str]:
    return sorted(str(subject) for subject in graph.subjects(predicate, object_))


def build_inventory(source: str | Path, *, format: str = "xml") -> dict[str, Any]:
    """Return a JSON-serializable inventory and source provenance record."""

    source_path = Path(source)
    source_bytes = source_path.read_bytes()
    graph = load_graph(source_path, format=format)

    class_iris = set(_iri_values(graph, RDF.type, OWL.Class))
    individual_iris = set(_iri_values(graph, RDF.type, OWL.NamedIndividual))
    annotation_property_iris = set(
        _iri_values(graph, RDF.type, OWL.AnnotationProperty)
    )
    object_property_iris = set(_iri_values(graph, RDF.type, OWL.ObjectProperty))
    datatype_property_iris = set(
        _iri_values(graph, RDF.type, OWL.DatatypeProperty)
    )

    class_roots = sorted(
        iri
        for iri in class_iris
        if not list(graph.objects(URIRef(iri), RDFS.subClassOf))
    )
    predicate_counts = Counter(str(predicate) for _, predicate, _ in graph)
    rdf_type_counts = Counter(
        str(object_) for _, _, object_ in graph.triples((None, RDF.type, None))
    )
    literal_count = sum(
        1 for _, _, object_ in graph if isinstance(object_, Literal)
    )

    return {
        "source": {
            "path": str(source_path.resolve()),
            "sha256": hashlib.sha256(source_bytes).hexdigest(),
            "format": format,
            "rdflib_version": rdflib_version,
        },
        "graph": {
            "triple_count": len(graph),
            "subject_count": len(set(graph.subjects())),
            "predicate_count": len(set(graph.predicates())),
            "literal_object_count": literal_count,
        },
        "entities": {
            "classes": sorted(class_iris),
            "class_count": len(class_iris),
            "class_roots": class_roots,
            "annotation_properties": sorted(annotation_property_iris),
            "annotation_property_count": len(annotation_property_iris),
            "object_properties": sorted(object_property_iris),
            "object_property_count": len(object_property_iris),
            "datatype_properties": sorted(datatype_property_iris),
            "datatype_property_count": len(datatype_property_iris),
            "named_individuals": sorted(individual_iris),
            "named_individual_count": len(individual_iris),
            "individuals_also_classes": sorted(individual_iris & class_iris),
        },
        "observed_counts": {
            "rdf_type_objects": dict(sorted(rdf_type_counts.items())),
            "predicates": dict(sorted(predicate_counts.items())),
        },
        "reasoning": {
            "inference_applied": False,
            "iri_rewriting_applied": False,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = build_inventory(args.source)
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
