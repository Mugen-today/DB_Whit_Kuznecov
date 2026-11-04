// Requires an offline write window and verified backup. Dry-run unless MIGRATION_APPLY=1.
try {
  load('/opt/storage/admin.js');
  const collections=[['Pdtient','Patient'],['Setlement','Settlement']];
  const fields=[['Municipality','setlement','settlement'],['Building','courpus','corpus'],['Patient','medical_record.сhronic_diseases','medical_record.chronic_diseases']];
  const present=new Set(db.getCollectionNames());
  for(const [oldName,newName] of collections)if(present.has(oldName)&&present.has(newName))throw new Error('Both collection names exist: '+oldName+' / '+newName);
  const physical=name=>collections.find(([oldName,newName])=>newName===name && present.has(oldName))?.[0]||name;
  for(const [name,oldField,newField] of fields) {
    if(db.getCollection(physical(name)).countDocuments({[oldField]:{$exists:true},[newField]:{$exists:true}},{limit:1}))
      throw new Error('Both field names exist in '+name+'; manual reconciliation required');
  }
  print('PLAN: Pdtient -> Patient; Setlement -> Settlement; three field renames; raw cases untouched');
  if(process.env.MIGRATION_APPLY==='1') {
    for(const [oldName,newName] of collections)if(present.has(oldName)) {
      const count=db.getCollection(oldName).countDocuments({});
      db.getCollection(oldName).renameCollection(newName,false);
      if(db.getCollection(newName).countDocuments({})!==count)throw new Error('Count changed during rename');
    }
    for(const [name,oldField,newField] of fields) {
      const c=db.getCollection(name);
      const before=c.countDocuments({[oldField]:{$exists:true}});
      const r=c.updateMany({[oldField]:{$exists:true},[newField]:{$exists:false}},{$rename:{[oldField]:newField}});
      if(r.modifiedCount!==before)throw new Error('Rename incomplete; stop writers and rerun preflight');
    }
    load('/opt/init/schema.js');load('/opt/init/indexes.js');load('/opt/init/roles.js');
    print('PASS migration applied; ObjectId values retained; source records not deleted');
  } else print('DRY RUN: no changes; apply with manage.py migrate after backup and stopping all writers');
} catch(error) {print('FAIL migration: '+error.message);quit(1);}
