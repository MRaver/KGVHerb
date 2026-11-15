"""Offline regression doubles: not proof of Neo4j/Cypher behavior."""
import copy
from dataclasses import replace
import json
from pathlib import Path
import unittest
from unittest.mock import Mock,patch

from rdflib import Literal,URIRef
from vietherb_ontology import target,writer
from vietherb_ontology import neo4j_io as io
from vietherb_ontology.import_plan import build_plan,plan_from_bytes,verify_plan
from vietherb_ontology.pipeline import (IntegrityError,canonical,decode_term,encode_term,
    export_rows,validate_records,validate_roundtrip,BASELINE_SHA256)

ROOT=Path(__file__).parents[1]


class FakeDriver:
    """Stateful rollback-aware Python double; deliberately does not parse Cypher."""
    def __init__(self):
        self.terms={}; self.triples={}; self.sources={}; self.snapshots={}; self.runs={}
        self.assertions={}; self.calls=[]; self.sessions=[]; self.inject={}
        self.databases=[{'name':'vietherb-test','databaseID':'test-id','type':'standard',
                         'currentStatus':'online','access':'read-write','aliases':[]}]
        self.info=[{'id':'test-id','name':'vietherb-test'}]
        self.constraints=[{'name':name,'type':'UNIQUENESS','entityType':'NODE',
                           'labelsOrTypes':[label],'properties':[prop]}
                          for name,(label,prop) in target.REQUIRED.items()]
        self.indexes=[{'owningConstraint':name,'state':'ONLINE','type':'RANGE',
                      'entityType':'NODE','labelsOrTypes':[label],'properties':[prop]}
                     for name,(label,prop) in target.REQUIRED.items()]
    def session(self,**kwargs):
        self.sessions.append(kwargs)
        return FakeSession(self)
    def run(self,query,**p):
        self.calls.append(query)
        if query in self.inject:
            effect=self.inject[query]
            if isinstance(effect,Exception): raise effect
            return effect(p)
        if query==target.DATABASES: return copy.deepcopy(self.databases)
        if query==target.DB_INFO: return copy.deepcopy(self.info)
        if query==target.CONSTRAINTS: return copy.deepcopy(self.constraints)
        if query==target.INDEXES: return copy.deepcopy(self.indexes)
        if query==target.COMPONENTS:
            return [{'name':'Neo4j Kernel','versions':['2026.10.2'],'edition':'enterprise'}]
        key,owner=p.get('key'),p.get('owner')
        if query==writer.LOOKUP_SOURCE:
            return [{'source':self.sources[p['sha']]}] if p['sha'] in self.sources else []
        if query==writer.LOOKUP_SNAPSHOT:
            return [self.snapshots[key]] if key in self.snapshots else []
        if query==writer.LOOKUP_RUN:
            return [self.runs[owner]] if owner in self.runs else []
        if query==writer.INIT:
            self.sources.setdefault(p['sha'],{'sha256':p['sha'],'byteCount':p['byteCount']})
            self.snapshots.setdefault(key,{'snapshot':{'key':key,'state':'LOADING','owner':owner,
                'manifestJson':p['manifest']},'sources':[p['sha']],'sourceCount':1})
            self.runs.setdefault(owner,{'run':{'id':owner,'status':'LOADING','snapshotKey':key,
                'identity':p['identity'],'metadataJson':p['metadata'],'startedUtc':p['started']},
                'targets':[key],'targetCount':1})
            return [{'key':key}]
        if query==io.GUARD:
            snap=self.snapshots[key]['snapshot']; run=self.runs[owner]['run']
            return [{'key':key}] if snap['state']=='LOADING' and snap['owner']==owner and run['status']=='LOADING' else []
        if query in (io.TERMS,io.TRIPLES):
            store=self.terms if query==io.TERMS else self.triples
            result=[]
            for rec in p['rows']:
                if query==io.TRIPLES and any(rec[k] not in self.terms for k in ('subjectKey','predicateKey','objectKey')):
                    continue
                store.setdefault(rec['key'],copy.deepcopy(rec))
                result.append({'payload':store[rec['key']]})
                if query==io.TRIPLES: self.assertions.setdefault(key,set()).add(rec['key'])
            return result
        if query==io.STATE:
            return [{'snapshot':self.snapshots[key]['snapshot']}] if key in self.snapshots else []
        if query==io.EXPORT:
            triples=[self.triples[k] for k in sorted(self.assertions.get(key,()))]
            used={t[k] for t in triples for k in ('subjectKey','predicateKey','objectKey')}
            return export_rows([self.terms[k] for k in used],triples)
        if query in (writer.FINISH,writer.FAILED):
            run=self.runs[owner]['run']; snap=self.snapshots[key]['snapshot']
            if run['identity']!=p['identity'] or run['status']!='LOADING': return []
            run.update(status='VALIDATED' if query==writer.FINISH else 'FAILED',finishedUtc=p['finished'])
            if query==writer.FINISH: snap['state']='VALIDATED'
            elif snap['state']=='LOADING' and snap['owner']==owner: snap['state']='FAILED'
            if query==writer.FAILED: run['failureCode']=p['failure']
            return [{'key':key}]
        raise AssertionError('Unrecognized fake query')


class FakeSession:
    def __init__(self,driver): self.driver=driver
    def __enter__(self): return self
    def __exit__(self,*args): pass
    def execute_read(self,callback,*args): return callback(self.driver,*args)
    def execute_write(self,callback,*args):
        fields=('terms','triples','sources','snapshots','runs','assertions')
        backup={k:copy.deepcopy(getattr(self.driver,k)) for k in fields}
        try: return callback(self.driver,*args)
        except Exception:
            for k,v in backup.items(): setattr(self.driver,k,v)
            raise


class BlockerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan=build_plan(ROOT/'VHO.owl',expected_sha256=BASELINE_SHA256)
        # Small source-backed fixture for fast lifecycle tests.
        cls.small=plan_from_bytes(b'''<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"><rdf:Description rdf:about="urn:test:s"><p xmlns="urn:test:">x</p></rdf:Description></rdf:RDF>''',base='urn:test:base')
    def writer(self,driver): return io.Neo4jWriter(driver,database='vietherb-test',enabled=True)
    def test_explicit_database_required(self):
        driver=Mock()
        with self.assertRaises(TypeError): io.Neo4jWriter(driver)
        for db in ('neo4j','system','NEO4J','other',' vietherb-test',None):
            with self.subTest(db=db),self.assertRaises(IntegrityError):
                io.Neo4jWriter(driver,database=db,enabled=True)
        driver.session.assert_not_called()
    def test_disabled_writer_never_opens_session(self):
        driver=Mock()
        with self.assertRaises(IntegrityError):
            io.Neo4jWriter(driver,database='vietherb-test').import_plan(self.plan,run_id='run')
        driver.session.assert_not_called()
    def test_manifest_fields_tamper_rejected_before_sessions(self):
        for field,value in (('snapshotKey','0'*64),('sourceSha256','0'*64),('parserPolicy','bad'),
                            ('mappingVersion','bad'),('contentFingerprint','0'*64),
                            ('effectiveBaseIRI','urn:changed'),('byteCount',0)):
            manifest=self.plan.manifest; manifest[field]=value
            bad=replace(self.plan,manifest_json=canonical(manifest)); driver=Mock()
            with self.subTest(field=field),self.assertRaises(IntegrityError):
                self.writer(driver).import_plan(bad,run_id='run')
            driver.session.assert_not_called()
    def test_source_bytes_tamper_rejected(self):
        with self.assertRaises(IntegrityError):
            verify_plan(replace(self.plan,source_bytes=self.small.source_bytes))
    def test_plan_duplicates_unused_malformed_and_missing_terms_rejected(self):
        terms=json.loads(self.small.terms_json)
        for modified in (terms+[terms[0]],terms+[encode_term(URIRef('urn:unused'))],terms[:-1],
                         [{**terms[0],'key':'bad'}]+terms[1:]):
            driver=Mock()
            with self.assertRaises(IntegrityError):
                self.writer(driver).import_plan(replace(self.small,terms_json=canonical(modified)),run_id='run')
            driver.session.assert_not_called()
    def test_bad_batch_settings_rejected_before_session(self):
        for setting in ({'max_rows':0},{'max_rows':True},{'max_bytes':2}):
            driver=Mock()
            with self.assertRaises((IntegrityError,ValueError)):
                self.writer(driver).import_plan(replace(self.small,**setting),run_id='run')
            driver.session.assert_not_called()
    def test_strict_boolean_and_string_payload(self):
        term=encode_term(Literal('x',lang='vn'))
        for field,value in (('languagePresent',1),('datatypePresent',0),('lexical',1),('key',True)):
            with self.subTest(field=field),self.assertRaises(IntegrityError):
                decode_term({**term,field:value})
        with self.assertRaises(IntegrityError): decode_term({**term,'extra':'bad'})
    def test_assertion_count_boolean_rejected(self):
        graph,_,terms,triples=verify_plan(self.small)
        result=export_rows(terms,triples); result[0]['assertionCount']=True
        self.assertFalse(validate_roundtrip(graph,result)[0]['passed'])
    def test_target_alias_and_id_rejected(self):
        for change in ('alias','id','offline','type','readonly','missing'):
            d=FakeDriver()
            if change=='alias': d.databases[0]['aliases']=['vietherb-test']
            if change=='id': d.info[0]['id']='protected-id'
            if change=='offline': d.databases[0]['currentStatus']='offline'
            if change=='type': d.databases[0]['type']='composite'
            if change=='readonly': d.databases[0]['access']='read-only'
            if change=='missing': d.databases=[]
            with self.subTest(change=change),self.assertRaises(IntegrityError):
                self.writer(d).import_plan(self.small,run_id='run')
            self.assertNotIn(writer.INIT,d.calls)
    def test_schema_and_index_rejected_before_init(self):
        for change in ('missing','shape','type','index','population'):
            d=FakeDriver()
            if change=='missing': d.constraints.pop()
            if change=='shape': d.constraints[0]['properties']=['other']
            if change=='type': d.constraints[0]['type']='NODE_KEY'
            if change=='index': d.indexes.pop()
            if change=='population': d.indexes[0]['state']='POPULATING'
            with self.subTest(change=change),self.assertRaises(IntegrityError):
                self.writer(d).import_plan(self.small,run_id='run')
            self.assertNotIn(writer.INIT,d.calls)
    def test_all_preflight_sessions_read_only(self):
        d=FakeDriver(); target.inspect_target(d,'vietherb-test')
        self.assertTrue(all(s['default_access_mode']=='READ' for s in d.sessions))
    def test_run_replay_and_new_run_idempotency(self):
        d=FakeDriver(); w=self.writer(d)
        for run in ('one','one','two'): self.assertTrue(w.import_plan(self.small,run_id=run)['passed'])
        self.assertEqual(len(d.runs),2)
        self.assertEqual(len(d.triples),1)
        self.assertEqual(d.calls.count(io.TRIPLES),1)
    def test_run_conflict_rolls_back_no_new_targets(self):
        d=FakeDriver(); w=self.writer(d); w.import_plan(self.small,run_id='one')
        before=copy.deepcopy((d.runs,d.snapshots,d.sources))
        with self.assertRaises(IntegrityError): w.import_plan(self.plan,run_id='one')
        self.assertEqual(before,(d.runs,d.snapshots,d.sources))
    def test_duplicate_metadata_edges_rejected(self):
        for kind in ('targets','sources'):
            d=FakeDriver(); w=self.writer(d); w.import_plan(self.small,run_id='one')
            if kind=='targets':
                d.runs['one']['targets']*=2; d.runs['one']['targetCount']=2
            else:
                snap=d.snapshots[self.small.manifest['snapshotKey']]
                snap['sources']*=2; snap['sourceCount']=2
            with self.subTest(kind=kind),self.assertRaises(IntegrityError): w.import_plan(self.small,run_id='one')
    def test_failed_import_lifecycle_and_safe_reason(self):
        d=FakeDriver(); d.inject[io.TERMS]=RuntimeError('secret must not persist')
        with self.assertRaisesRegex(RuntimeError,'secret must not persist'):
            self.writer(d).import_plan(self.small,run_id='one')
        self.assertEqual(d.runs['one']['run']['status'],'FAILED')
        self.assertEqual(d.snapshots[self.small.manifest['snapshotKey']]['snapshot']['state'],'FAILED')
        self.assertNotIn('secret',canonical(d.runs))
        self.assertEqual(d.terms,{})
    def test_failed_audit_preserves_original_error(self):
        d=FakeDriver(); original=RuntimeError('original')
        d.inject[io.TERMS]=original; d.inject[writer.FAILED]=RuntimeError('audit unavailable')
        with self.assertRaises(RuntimeError) as raised: self.writer(d).import_plan(self.small,run_id='one')
        self.assertIs(raised.exception,original)
        self.assertTrue(raised.exception.__notes__)
    def test_rerun_validation_failure_preserves_validated_snapshot(self):
        d=FakeDriver(); w=self.writer(d); w.import_plan(self.small,run_id='one')
        d.inject[io.EXPORT]=lambda p:[]
        with self.assertRaises(IntegrityError): w.import_plan(self.small,run_id='two')
        self.assertEqual(d.runs['two']['run']['status'],'FAILED')
        self.assertEqual(d.snapshots[self.small.manifest['snapshotKey']]['snapshot']['state'],'VALIDATED')
    def test_initialization_failure_rolls_back(self):
        d=FakeDriver(); d.inject[writer.INIT]=lambda p:[]
        with self.assertRaises(IntegrityError): self.writer(d).import_plan(self.small,run_id='one')
        self.assertEqual(d.runs,{})
        self.assertNotIn(writer.FAILED,d.calls)
    def test_failure_audit_missing_row_is_reported_not_silenced(self):
        d=FakeDriver(); original=RuntimeError('original')
        d.inject[io.TERMS]=original; d.inject[writer.FAILED]=lambda p:[]
        with self.assertRaises(RuntimeError) as raised: self.writer(d).import_plan(self.small,run_id='one')
        self.assertIs(raised.exception,original)
        self.assertTrue(raised.exception.__notes__)
    def test_run_metadata_complete_no_caller_secrets(self):
        d=FakeDriver(); self.writer(d).import_plan(self.small,run_id='one')
        run=d.runs['one']['run']; data=json.loads(run['metadataJson'])
        for key in ('settings','versions','codeHashes','gitHead','gitDirty','startedUtc','databaseID'):
            self.assertIn(key,data)
        self.assertIn('finishedUtc',run)

    def test_missing_match_rows_fail_without_publishing(self):
        d=FakeDriver(); d.inject[io.TRIPLES]=lambda p:[]
        with self.assertRaises(IntegrityError): self.writer(d).import_plan(self.small,run_id='one')
        self.assertEqual(d.runs['one']['run']['status'],'FAILED')
        self.assertEqual(d.triples,{})
        self.assertNotIn(writer.FINISH,d.calls)

    def test_orphan_loading_snapshot_rejected(self):
        d=FakeDriver(); self.writer(d).import_plan(self.small,run_id='one')
        key=self.small.manifest['snapshotKey']
        d.snapshots[key]['snapshot']['state']='LOADING'
        d.runs.clear()
        with self.assertRaises(IntegrityError): self.writer(d).import_plan(self.small,run_id='one')

    def test_invalid_language_is_validation_failure_not_uncaught_valueerror(self):
        graph,_,terms,triples=verify_plan(self.small)
        result=export_rows(terms,triples)
        result[0]['objects'][0]=encode_term(Literal('x',lang='vn'))
        result[0]['objects'][0]['language']='not valid language'
        self.assertFalse(validate_roundtrip(graph,result)[0]['passed'])

    def test_standalone_record_validation_rejects_unreferenced_duplicates(self):
        _,_,terms,triples=verify_plan(self.small)
        for changed in (terms+[terms[0]],terms+[encode_term(URIRef('urn:unused'))]):
            with self.assertRaises(IntegrityError): validate_records(changed,triples)

    def test_check_payloads_does_not_equate_bool_and_integer(self):
        term=encode_term(Literal('x',lang='en'))
        with self.assertRaises(IntegrityError):
            io.check_payloads([term],[{'payload':{**term,'languagePresent':1}}])

    def test_loose_manifest_api_no_longer_exists(self):
        self.assertFalse(hasattr(self.writer(Mock()),'import_graph'))

    def test_runner_offline_never_constructs_driver(self):
        from vietherb_ontology.integration_runner import run
        factory=Mock(side_effect=AssertionError('Network forbidden'))
        with patch.dict('os.environ',{'NEO4J_USERNAME':'fake','NEO4J_PASSWORD':'fake'}):
            result=run(['--database','vietherb-test','--source',str(ROOT/'VHO.owl')],driver_factory=factory)
        self.assertTrue(result['validation']['passed'])
        self.assertFalse(result['connectionOpened'])
        factory.assert_not_called()

    def test_runner_write_gate_rejects_without_confirmation(self):
        from vietherb_ontology.integration_runner import run
        factory=Mock()
        for args in (['--execute-writes'],['--execute-writes','--confirm-database','neo4j','--exclusive-writer'],
                     ['--execute-writes','--confirm-database','vietherb-test']):
            with self.assertRaises(IntegrityError):
                run(['--database','vietherb-test',*args],driver_factory=factory)
        factory.assert_not_called()

    def test_runner_read_only_mode_never_runs_write_callbacks(self):
        from vietherb_ontology.integration_runner import run
        d=FakeDriver()
        class Context:
            def __enter__(self): return d
            def __exit__(self,*args): pass
        with patch.dict('os.environ',{'NEO4J_USERNAME':'fake','NEO4J_PASSWORD':'fake'}):
            result=run(['--database','vietherb-test','--read-only','--source',str(ROOT/'VHO.owl')],
                       driver_factory=lambda *a,**k:Context())
        self.assertEqual(result['mode'],'read-only')
        self.assertNotIn(writer.INIT,d.calls)
        self.assertTrue(all(s['default_access_mode']=='READ' for s in d.sessions))


if __name__=='__main__': unittest.main()
