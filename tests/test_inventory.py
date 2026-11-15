import hashlib
import tempfile
import unittest
from pathlib import Path

from rdflib import Graph, Namespace, RDF, RDFS, OWL, Literal
from vietherb_ontology.pipeline import BASELINE_SHA256

from vietherb_ontology.inventory import build_inventory, load_graph


ROOT = Path(__file__).parents[1]
ONTOLOGY = ROOT / "VHO.owl"
VHO = Namespace("http://www.semanticweb.org/metruoi/ontologies/2017/2/VHO#")


class InventoryTests(unittest.TestCase):
    def test_real_ontology_inventory_is_observed_without_inference(self):
        inventory = build_inventory(ONTOLOGY)

        self.assertEqual(inventory["graph"]["triple_count"], 2646)
        self.assertEqual(inventory["entities"]["class_count"], 1262)
        self.assertEqual(inventory["entities"]["annotation_property_count"], 18)
        self.assertEqual(inventory["entities"]["object_property_count"], 0)
        self.assertEqual(inventory["entities"]["datatype_property_count"], 0)
        self.assertEqual(inventory["entities"]["named_individual_count"], 6)
        self.assertEqual(inventory['entities']['class_roots'], sorted(str(VHO[n]) for n in
            ('distribution','effect','fungi_kingdom','metabolite','morphology','plantae_family')))
        self.assertEqual(
            inventory["entities"]["individuals_also_classes"],
            sorted(str(iri) for iri in [
                VHO["alpha-amyrin"], VHO["beta-amyrin"], VHO["ellagic_acid"],
                VHO["euphorbianin"], VHO["rutin"], VHO["taraxerol"],
            ]),
        )
        self.assertFalse(inventory["reasoning"]["inference_applied"])

    def test_source_hash_is_reproducible(self):
        inventory = build_inventory(ONTOLOGY)
        expected = hashlib.sha256(ONTOLOGY.read_bytes()).hexdigest()
        self.assertEqual(inventory["source"]["sha256"], expected)
        self.assertEqual(expected, BASELINE_SHA256)
        self.assertEqual(inventory["source"]["rdflib_version"], "7.6.0")

    def test_parser_preserves_original_iri_and_literal(self):
        graph = Graph()
        graph.add((VHO["example/entity"], RDF.type, OWL.Class))
        graph.add((VHO["example/entity"], RDFS.label, Literal('Cây thuốc',lang='vn')))
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            source = Path(directory) / "sample.ttl"
            graph.serialize(destination=source, format="turtle")
            parsed = load_graph(source, format="turtle")

        self.assertIn((VHO["example/entity"], RDF.type, OWL.Class), parsed)
        self.assertIn(
            (VHO["example/entity"], RDFS.label, Literal('Cây thuốc',lang='vn')), parsed
        )


if __name__ == "__main__":
    unittest.main()
