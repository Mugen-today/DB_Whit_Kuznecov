// Executes in a SEPARATE container: real DNS + TCP + MongoDB auth + BSON.
try {
  const host=process.env.STORAGE_TEST_HOST;
  if(host!=='storage') throw new Error('Unexpected host');
  function connect(user,password) {
    const c=new Mongo('mongodb://storage:27017/?serverSelectionTimeoutMS=5000&connectTimeoutMS=3000');
    const s=c.getDB('Schema');
    if(!s.auth(user,password)) throw new Error('Authentication failed');
    return s;
  }
  const reader=connect('analyst',process.env.READER_PASSWORD);
  const ingest=connect('etl_ingest',process.env.INGEST_PASSWORD);
  const processor=connect('etl_processor',process.env.PROCESSOR_PASSWORD);
  const guest=connect('guest',process.env.GUEST_PASSWORD);
  const user=connect('app_user',process.env.USER_PASSWORD);
  guest.Patient.findOne({}); user.Patient.findOne({});
  for(const name of ['Social_group','Street','Building','Placement']) {
    let denied=false;try{guest.getCollection(name).findOne({});}catch(e){if(e.code===13)denied=true;else throw e;}
    if(!denied)throw new Error('Guest has excessive permissions');
  }
  reader.cases.findOne({}); ingest.cases.findOne({}); processor.Gender.findOne({});
  // A read that is always forbidden for the ingest role; no mutation in ordinary checks.
  let denied=false;
  try { ingest.Gender.findOne({}); } catch(e) { if(e.code===13) denied=true; else throw e; }
  if(!denied) throw new Error('Ingest has excessive permissions');
  if(process.env.TEST_WRITES==='1') {
    const id=new ObjectId();
    const doc={_id:id,source:'integration-test',imported_at:new Date(),raw:{text:'Тест передачи',age:25,geometry:{type:'Point',coordinates:[30.3,59.94]},values:[1,null,'a']}};
    ingest.cases.insertOne(doc,{writeConcern:{w:1,j:true}});
    const received=reader.cases.findOne({_id:id});
    if(EJSON.stringify(received)!==EJSON.stringify(doc)) throw new Error('BSON roundtrip differs');
    function forbidden(action){let refused=false;try{action();}catch(e){if(e.code===13)refused=true;else throw e;}if(!refused)throw new Error('Forbidden write allowed');}
    forbidden(()=>guest.Patient.insertOne({_id:new ObjectId()}));
    forbidden(()=>user.createCollection('Forbidden_schema_change'));
    forbidden(()=>reader.cases.insertOne({_id:new ObjectId()}));
    forbidden(()=>processor.cases.updateOne({_id:id},{$set:{source:'wrong'}}));
    const modelId=new ObjectId();
    processor.Gender.insertOne({_id:modelId,type:'test'});
    processor.Gender.updateOne({_id:modelId},{$set:{type:'updated'}});
    if(reader.Gender.findOne({_id:modelId}).type!=='updated') throw new Error('Model update failed');
    let invalid=false;
    try{processor.Gender.insertOne({type:123});}catch(e){if(e.code===121)invalid=true;else throw e;}
    if(!invalid)throw new Error('Schema validation failed');
    forbidden(()=>ingest.cases.deleteOne({_id:id}));
    print('PASS isolated insert/read BSON roundtrip, model update, validators and write denials');
  }
  print('PASS container DNS/TCP, service auth, reads and ingest RBAC');
} catch (_) { print('FAIL cross-container Storage contract'); quit(1); }
