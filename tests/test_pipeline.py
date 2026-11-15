"""Technical synthetic RDF only; no medical evidence asserted."""
import copy
from pathlib import Path
import unittest
from unittest.mock import Mock, MagicMock

from rdflib import URIRef, Literal, RDF, OWL, XSD
from vietherb_ontology.pipeline import (
    BASELINE_SHA256, IntegrityError, canonical, parse_bytes, parse_source,
    encode_term, decode_term, encode_graph, export_rows, plan_batches, validate_roundtrip)
from vietherb_ontology.neo4j_io import (
    GUARD, TERMS, TRIPLES, STATE, EXPORT, Neo4jWriter,
    check_payloads, write_terms, write_triples, export_snapshot)

ROOT=Path(__file__).parents[1]
FIXTURE='''@prefix t: <urn:test:> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
t:C a owl:Class, owl:NamedIndividual ;
 t:undeclared "01"^^xsd:integer, "1"^^xsd:integer,
 "Cây thuốc"@vn, "Tree"@en, "", "1.00"^^xsd:decimal,
 "true"^^xsd:boolean, "2026-11-15T00:00:00Z"^^xsd:dateTime ;
 t:multi "one", "two" ; t:unicode <urn:test:cây/α#β> .'''.encode('utf-8')


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.graph=parse_bytes(FIXTURE,format='turtle')
        self.terms,self.triples=encode_graph(self.graph)
        self.rows=export_rows(self.terms,self.triples)

    def test_synthetic_roundtrip(self):
        report,decoded=validate_roundtrip(self.graph,self.rows)
        self.assertTrue(report['passed'])
        self.assertIn((URIRef('urn:test:C'),RDF.type,OWL.Class),decoded)
        self.assertIn((URIRef('urn:test:C'),RDF.type,OWL.NamedIndividual),decoded)
        self.assertEqual(len(list(decoded.objects(URIRef('urn:test:C'),URIRef('urn:test:multi')))),2)

    def test_typed_lexical_forms_remain_distinct(self):
        values=list(self.graph.objects(URIRef('urn:test:C'),URIRef('urn:test:undeclared')))
        self.assertIn('01',[str(v) for v in values])
        self.assertNotEqual(encode_term(Literal('01',datatype=XSD.integer,normalize=False)),
                            encode_term(Literal('1',datatype=XSD.integer,normalize=False)))

    def test_literal_variants(self):
        for literal in (Literal('a\n"\\α',lang='vn'),Literal(''),Literal('x',datatype=XSD.string),
                        Literal('01',datatype=XSD.integer,normalize=False)):
            with self.subTest(literal=repr(literal)):
                actual=decode_term(encode_term(literal))
                self.assertEqual((str(actual),actual.datatype,actual.language),
                                 (str(literal),literal.datatype,literal.language))

    def test_unicode_not_normalized(self):
        self.assertNotEqual(encode_term(URIRef('urn:test:é')),encode_term(URIRef('urn:test:e\u0301')))

    def test_blank_nodes_rejected(self):
        with self.assertRaises(IntegrityError):
            parse_bytes(b'<urn:s> <urn:p> [] .',format='turtle')

    def test_entities_rejected(self):
        with self.assertRaises(IntegrityError):
            parse_bytes(b'<!DOCTYPE x><x/>')

    def test_source_hash_rejected(self):
        with self.assertRaises(IntegrityError):
            parse_source(ROOT/'VHO.owl','0'*64)

    def test_baseline_roundtrip_and_counts(self):
        graph,manifest=parse_source(ROOT/'VHO.owl',BASELINE_SHA256)
        terms,triples=encode_graph(graph)
        self.assertEqual(len(triples),2646)
        self.assertEqual(sum(t['kind']=='iri' for t in terms),1288)
        self.assertEqual(sum(t['kind']=='literal' for t in terms),97)
        self.assertTrue(validate_roundtrip(graph,export_rows(terms,triples))[0]['passed'])
        self.assertEqual(manifest,parse_source(ROOT/'VHO.owl',BASELINE_SHA256)[1])

    def test_batches_deterministic_and_bounded(self):
        batches=plan_batches(self.terms,max_rows=2,max_bytes=1500)
        self.assertEqual(batches,plan_batches(list(reversed(self.terms)),max_rows=2,max_bytes=1500))
        self.assertEqual(sum(batches,[]),self.terms)
        self.assertTrue(all(len(b)<=2 and len(canonical(b).encode())<=1500 for b in batches))

    def test_oversized_and_duplicate_batch_rejected(self):
        for records,limit in ((self.terms,3),([self.terms[0]]*2,10000)):
            with self.assertRaises(IntegrityError):
                plan_batches(records,max_bytes=limit)

    def test_missing_extra_and_duplicate_rows(self):
        for rows in (self.rows[:-1],self.rows+[self.rows[0]]):
            with self.subTest(size=len(rows)):
                self.assertFalse(validate_roundtrip(self.graph,rows)[0]['passed'])
        self.assertGreater(validate_roundtrip(set(),self.rows)[0]['extra'],0)

    def test_role_and_assertion_corruption(self):
        for role,value in (('subjects',[]),('predicates',[]),('objects',[]),
                           ('subjects',self.rows[0]['subjects']*2),('assertionCount',2)):
            rows=copy.deepcopy(self.rows); rows[0][role]=value
            with self.subTest(role=role):
                self.assertGreater(validate_roundtrip(self.graph,rows)[0]['mismatch'],0)

    def test_term_and_triple_payload_corruption(self):
        for field in ('key','subjectKey','objectKey'):
            rows=copy.deepcopy(self.rows); rows[0]['triple'][field]='bad'
            self.assertFalse(validate_roundtrip(self.graph,rows)[0]['passed'])
        term=encode_term(Literal('Tree',lang='en'))
        for field,value in (('lexical','wrong'),('language','wrong'),('datatype','wrong')):
            changed={**term,field:value}
            with self.assertRaises(IntegrityError): decode_term(changed)

    def test_invalid_snapshot_state(self):
        for state in ('FAILED','NEW','DELETED'):
            with self.assertRaises(IntegrityError): validate_roundtrip(self.graph,self.rows,state)


class TransactionDouble:
    def __init__(self,responses):
        self.responses=responses; self.calls=[]
    def run(self,query,**params):
        self.calls.append((query,params))
        response=self.responses[query]
        return response(params) if callable(response) else response


class AdapterTests(unittest.TestCase):
    def test_writer_full_flow_with_session_double(self):
        from test_blockers import FakeDriver
        from vietherb_ontology.import_plan import build_plan
        plan=build_plan(ROOT/'VHO.owl',expected_sha256=BASELINE_SHA256)
        driver=FakeDriver()
        writer=Neo4jWriter(driver,database='vietherb-test',enabled=True)
        self.assertTrue(writer.import_plan(plan,run_id='run1')['passed'])
        before=(len(driver.terms),len(driver.triples))
        self.assertEqual(before,(1385,2646))
        self.assertTrue(writer.import_plan(plan,run_id='run2')['passed'])
        self.assertEqual(before,(len(driver.terms),len(driver.triples)))

    def test_failed_preflight_never_opens_session(self):
        driver=Mock()
        with self.assertRaises(IntegrityError):
            Neo4jWriter(driver,database='vietherb-test',enabled=True).import_plan(None,run_id='run')
        driver.session.assert_not_called()

    def test_writer_disabled_without_session(self):
        driver=Mock()
        with self.assertRaises(IntegrityError):
            Neo4jWriter(driver,database='vietherb-test').import_plan(None,run_id='test')
        driver.session.assert_not_called()

    def test_term_write_payload_checks(self):
        batch=[encode_term(URIRef('urn:test:x'))]
        for stored in ([],[{'payload':{**batch[0],'iri':'wrong'}}]):
            tx=TransactionDouble({GUARD:[{'key':'snap'}],TERMS:stored})
            with self.assertRaises(IntegrityError): write_terms(tx,'snap','run',batch)
        tx=TransactionDouble({GUARD:[{'key':'snap'}],TERMS:[{'payload':batch[0]}]})
        write_terms(tx,'snap','run',batch)
        write_terms(tx,'snap','run',batch)  # replay returns identical payload

    def test_snapshot_guard_precedes_writes(self):
        tx=TransactionDouble({GUARD:[]})
        with self.assertRaises(IntegrityError): write_terms(tx,'snap','run',[])
        self.assertEqual(len(tx.calls),1)

    def test_missing_match_and_duplicate_return_rows(self):
        graph=parse_bytes(FIXTURE,format='turtle'); _,triples=encode_graph(graph)
        batch=triples[:1]
        for result in ([],[{'payload':batch[0]}]*2,[{'payload':{**batch[0],'objectKey':'bad'}}]):
            tx=TransactionDouble({GUARD:[{'key':'snap'}],TRIPLES:result})
            with self.assertRaises(IntegrityError): write_triples(tx,'snap','run',batch)

    def test_export_state_visibility(self):
        for state in ('FAILED','LOADING'):
            tx=TransactionDouble({STATE:[{'snapshot':{'state':state,'owner':'run'}}],EXPORT:[]})
            with self.assertRaises(IntegrityError): export_snapshot(tx,'snap')
        tx=TransactionDouble({STATE:[{'snapshot':{'state':'LOADING','owner':'run'}}],EXPORT:[]})
        self.assertEqual(export_snapshot(tx,'snap',allow_loading=True,owner='run'),[])
        with self.assertRaises(IntegrityError): export_snapshot(tx,'snap',allow_loading=True,owner='other')

    def test_export_keeps_corrupt_structural_envelope(self):
        corrupt={'triple':{},'subjects':[],'predicates':[],'objects':[],'assertionCount':2}
        tx=TransactionDouble({STATE:[{'snapshot':{'state':'VALIDATED'}}],EXPORT:[corrupt]})
        self.assertEqual(export_snapshot(tx,'snap'),[corrupt])


if __name__=='__main__': unittest.main()
