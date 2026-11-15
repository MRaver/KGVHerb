"""Offline-only CLI. No database configuration or connection code."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
import time

import rdflib
import neo4j

from .pipeline import (BASELINE_SHA256, parse_source, parse_bytes, encode_graph,
                       export_rows, plan_batches, validate_roundtrip, IntegrityError)
from .inventory import build_inventory
from .import_plan import build_plan,verify_plan


def run(source, output):
    started = time.perf_counter()
    plan=build_plan(source,expected_sha256=BASELINE_SHA256)
    graph,manifest,terms,triples=verify_plan(plan)
    term_batches, triple_batches = plan_batches(terms), plan_batches(triples)
    report, decoded = validate_roundtrip(graph, export_rows(terms, triples))
    reparsed = parse_bytes(decoded.serialize(format='nt', encoding='utf-8'), format='nt')
    serialized_report, _ = validate_roundtrip(graph, export_rows(*encode_graph(reparsed)))
    inventory = build_inventory(source)
    counts = Counter(r['kind'] for r in terms)
    acceptance = {'sha256': manifest['sourceSha256'] == BASELINE_SHA256,
                  'triples':len(triples)==2646, 'roots':len(inventory['entities']['class_roots'])==6,
                  'iriTerms':counts['iri']==1288, 'literalTerms':counts['literal']==97,
                  'strictRoundtrip':report['passed'], 'serializedRoundtrip':serialized_report['passed']}
    root = Path(__file__).resolve().parents[2]
    def git(*args):
        return subprocess.check_output(['git', *args], cwd=root, text=True).strip()
    manifest.update({'createdUtc':datetime.now(timezone.utc).isoformat(),
                     'versions':{'python':sys.version,'rdflib':rdflib.__version__,
                                 'neo4jDriver':neo4j.__version__,'os':platform.platform(), 'server':'not_measured'},
                     'gitHead':git('rev-parse','HEAD'), 'gitDirty':bool(git('status','--porcelain')),
                     'codeHashes':{str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest()
                                   for folder in ('src','tests') for p in sorted((root/folder).rglob('*.py'))},
                     'settings':{'maxRows':500,'maxBytes':4194304,'databaseOperations':False},
                     'batches':{'terms':len(term_batches),'triples':len(triple_batches)}})
    report.update({'mode':'offline','acceptance':acceptance,'passed':all(acceptance.values()),
                   'iriTerms':counts['iri'],'uniqueLiteralTerms':counts['literal'],
                   'roots':inventory['entities']['class_roots'], 'sourceSha256':manifest['sourceSha256'],
                   'serializedRoundtrip':serialized_report['passed'],
                   'wallSeconds':time.perf_counter()-started, 'dbWriteSeconds':'not_measured',
                   'peakMemory':'not_measured','databaseOperations':False})
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    for name, data in [('source_manifest.json',manifest),('validation_report.json',report),('ontology_inventory.json',inventory)]:
        (output/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (output/'VALIDATION_REPORT.md').write_text(
        '# RDF importer — Offline validation\n\n'
        + f"Passed: {report['passed']}. Database operations: false.\n\n"
        + f"SHA-256: `{manifest['sourceSha256']}`\n\n"
        + f"Triples: {len(triples)}; roots: {len(inventory['entities']['class_roots'])}; IRI terms: {counts['iri']}; literal terms: {counts['literal']}.\n\n"
        + f"Missing: {report['missing']}; extra: {report['extra']}; mismatch: {report['mismatch']}.\n\n"
        + 'Strict lexical/datatype/language and serialized N-Triples round-trips checked.\n\n'
        + 'See [manifest](source_manifest.json) and [raw validation](validation_report.json).\n\n'
        + 'Neo4j Cypher, constraints, concurrency, server compatibility and performance remain unverified.\n',encoding='utf-8')
    if not report['passed']:
        raise IntegrityError('Offline acceptance failed; inspect report')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    report=run(args.source,args.output)
    print(json.dumps({k:report[k] for k in ('passed','decodedTriples','missing','extra','mismatch')},indent=2))


if __name__ == '__main__':
    main()
