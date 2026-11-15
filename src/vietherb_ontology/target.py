"""Read-only target/schema gates; never executes DDL."""
from neo4j import READ_ACCESS
from .pipeline import IntegrityError

TEST_DATABASE='vietherb-test'
DATABASES='SHOW DATABASES YIELD name, type, aliases, currentStatus, databaseID, access'
DB_INFO='CALL db.info()'
CONSTRAINTS='SHOW CONSTRAINTS'
INDEXES='SHOW INDEXES'
COMPONENTS='CALL dbms.components()'
REQUIRED={'rdf_term_key':('RdfTerm','key'),'rdf_triple_key':('RdfTriple','key'),
          'rdf_source_hash':('SourceArtifact','sha256'),
          'rdf_snapshot_key':('ImportSnapshot','key'),'rdf_run_id':('ImportRun','id')}


def require_target(database):
    if type(database) is not str or database != TEST_DATABASE:
        raise IntegrityError('Only explicit vietherb-test is permitted')


def inspect_target(driver,database):
    require_target(database)
    def read(session,query):
        return session.execute_read(lambda tx:[dict(r) for r in tx.run(query)])
    with driver.session(database='system',default_access_mode=READ_ACCESS) as session:
        databases=read(session,DATABASES)
    found=[r for r in databases if r.get('name')==database]
    if len(found)!=1:
        raise IntegrityError('Target database missing or ambiguous')
    target=found[0]
    if (target.get('type')!='standard' or target.get('currentStatus')!='online'
            or target.get('access')!='read-write' or not target.get('databaseID')):
        raise IntegrityError('Target must be online, standard and writable')
    for row in databases:
        if type(row.get('aliases')) is not list or database in row['aliases']:
            raise IntegrityError('Cannot resolve unambiguous database target')
    with driver.session(database=database,default_access_mode=READ_ACCESS) as session:
        info=read(session,DB_INFO)
        if (len(info)!=1 or info[0].get('name')!=database
                or str(info[0].get('id'))!=str(target['databaseID'])):
            raise IntegrityError('Resolved database identity mismatch')
        constraints=read(session,CONSTRAINTS)
        indexes=read(session,INDEXES)
        components=read(session,COMPONENTS)
    for name,(label,prop) in REQUIRED.items():
        found=[r for r in constraints if r.get('name')==name]
        if len(found)!=1 or any(found[0].get(k)!=v for k,v in
                {'entityType':'NODE','labelsOrTypes':[label],'properties':[prop]}.items()):
            raise IntegrityError('Required uniqueness constraint shape missing')
        if found[0].get('type') not in ('UNIQUENESS','NODE_PROPERTY_UNIQUENESS'):
            raise IntegrityError('Wrong constraint type')
        backing=[r for r in indexes if r.get('owningConstraint')==name]
        if (len(backing)!=1 or any(backing[0].get(k)!=v for k,v in
                {'state':'ONLINE','entityType':'NODE','labelsOrTypes':[label],
                 'properties':[prop],'type':'RANGE'}.items())):
            raise IntegrityError('Backing index missing or not ONLINE')
    return {'database':database,'databaseID':target['databaseID'],
            'constraints':constraints,'indexes':indexes,'serverComponents':components}
