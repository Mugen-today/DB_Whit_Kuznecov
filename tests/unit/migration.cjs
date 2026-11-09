// Execute the ACTUAL migration with a small persistent mock. No MongoDB claimed.
const fs=require('fs'),vm=require('vm'),assert=require('assert/strict'),path=require('path');
const code=fs.readFileSync(path.join(__dirname,'../../storage/migrations/rename-v7.js'),'utf8');
const get=(d,p)=>p.split('.').reduce((o,k)=>o?.[k],d);
const put=(d,p,v)=>{const parts=p.split('.'),last=parts.pop();let o=d;for(const k of parts)o=o[k]??={};o[last]=v;};
const del=(d,p)=>{const parts=p.split('.'),last=parts.pop();let o=d;for(const k of parts)o=o[k];delete o[last];};
function run(data,apply){
 let changed=0;const matches=(d,q)=>Object.entries(q).every(([k,v])=>v.$exists===(get(d,k)!==undefined));
 function collection(name){return {
  countDocuments(q={}){return (data[name]||[]).filter(d=>matches(d,q)).length;},
  renameCollection(to,drop){assert.equal(drop,false);if(data[to])throw Error('Target exists');data[to]=data[name];delete data[name];changed++;},
  updateMany(q,op){let modifiedCount=0;for(const d of data[name]||[])if(matches(d,q)){for(const [a,b] of Object.entries(op.$rename)){put(d,b,get(d,a));del(d,a);}modifiedCount++;changed++;}return {modifiedCount};}
 };}
 let failed=false;
 try{vm.runInNewContext(code,{db:{getCollectionNames:()=>Object.keys(data),getCollection:collection},load:()=>{},print:()=>{},process:{env:{MIGRATION_APPLY:apply?'1':'0'}},quit:n=>{throw Error('exit '+n);}});}catch(e){failed=true;}
 return {changed,failed};
}
let data={Pdtient:[{_id:'stable',medical_record:{'сhronic_diseases':'original'}}],Setlement:[{_id:'s'}],Municipality:[{setlement:'s'}],Building:[{courpus:0}],cases:[{raw:{courpus:'unchanged'}}]};
let before=JSON.stringify(data);assert.equal(run(data,false).changed,0);assert.equal(JSON.stringify(data),before);
assert.equal(run(data,true).failed,false);assert.equal(data.Patient[0]._id,'stable');assert.equal(data.Patient[0].medical_record.chronic_diseases,'original');assert.equal(data.Building[0].corpus,0);assert.equal(data.cases[0].raw.courpus,'unchanged');assert.equal(run(data,true).changed,0);
for(const conflict of [{Pdtient:[{}],Patient:[{}]},{Municipality:[{setlement:'a',settlement:'b'}]}]){const snapshot=JSON.stringify(conflict);const r=run(conflict,true);assert(r.failed);assert.equal(r.changed,0);assert.equal(JSON.stringify(conflict),snapshot);}
console.log('PASS migration dry-run, repeat, preservation of IDs/values, collision preflight; mock only');
