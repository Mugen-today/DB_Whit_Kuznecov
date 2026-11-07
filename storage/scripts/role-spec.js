// Shared policy for provisioning AND verification. No wildcards for guest.
function roleSpec(spec) {
  const names=Object.values(spec.collections).map(e=>e.ns.slice(7));
  const resource=collection=>({db:'Schema',collection});
  const restricted=new Set(['Social_group','Street','Building','Placement']);
  const modelWrites=names.map(collection=>({resource:resource(collection),actions:['find','insert','update']}));
  return {
    ingest_append:{privileges:[{resource:resource('cases'),actions:['find','insert']}],roles:[]},
    processor_write:{privileges:[{resource:resource('cases'),actions:['find']},...modelWrites],roles:[]},
    gis_admin:{privileges:[],roles:[{role:'root',db:'admin'}]},
    gis_user:{privileges:[{resource:resource('cases'),actions:['find']},...modelWrites],roles:[]},
    gis_guest:{privileges:[...names,'cases'].filter(n=>!restricted.has(n)).map(collection=>({resource:resource(collection),actions:['find']})),roles:[]}
  };
}
function accountSpec() {
  return [['etl_ingest','INGEST_PASSWORD','ingest_append'],['etl_processor','PROCESSOR_PASSWORD','processor_write'],
    ['analyst','READER_PASSWORD','read'],['app_user','USER_PASSWORD','gis_user'],['guest','GUEST_PASSWORD','gis_guest']];
}

function roleDatabase(name) { return name==='gis_admin'?'admin':'Schema'; }
