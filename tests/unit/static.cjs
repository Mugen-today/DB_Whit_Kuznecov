const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const model = JSON.parse(fs.readFileSync(path.join(__dirname,'../../storage/schema/model.json')));
const collections = new Map(), roles = new Map(), adminRoles = new Map(), users = new Map();
const adminDatabase = {getRole:n=>adminRoles.get(n), createRole:r=>adminRoles.set(r.role,r), updateRole:(n,r)=>adminRoles.set(n,r)};
function coll(name) { return {createIndex(spec) {assert(Object.keys(spec).length);}}; }
const database = {
  getCollectionNames:()=>[...collections.keys()],
  createCollection:(n,o)=>{assert(!collections.has(n)); collections.set(n,o);},
  runCommand:({collMod,...o})=>{collections.set(collMod,o);return {ok:1};},
  getCollection:coll,
  cases:coll('cases'), Instances:coll('Instances'),
  getRole:n=>roles.get(n), createRole:r=>{assert(r.roles.every(x=>x.db==='Schema'));roles.set(r.role,r);},
  updateRole:(n,r)=>roles.set(n,r),
  getSiblingDB:()=>database, getUser:n=>users.get(n),createUser:u=>users.set(u.user,u),updateUser:(n,u)=>users.set(n,{...users.get(n),...u})
};
const code=fs.readFileSync(path.join(__dirname,'../../storage/init/bootstrap.js'),'utf8');
function run() {const context=vm.createContext({
  require:n=>{assert.equal(n,'fs');return {readFileSync:()=>JSON.stringify(model)};},
  db:{getSiblingDB:n=>{assert(['Schema','admin'].includes(n));return n==='admin'?adminDatabase:database;}},
  process:{env:{INGEST_PASSWORD:'a',PROCESSOR_PASSWORD:'b',READER_PASSWORD:'c',USER_PASSWORD:'d',GUEST_PASSWORD:'e'}},print:()=>{}
}); context.load=file=>{assert(file.startsWith('/opt/init/')||file.startsWith('/opt/storage/'));vm.runInContext(fs.readFileSync(path.join(__dirname,file.startsWith('/opt/init/')?'../../storage/init':'../../storage/scripts',path.basename(file)),'utf8'),context);}; vm.runInContext(code,context);}
run(); const password=users.get('analyst').pwd; run(); assert.equal(users.get('analyst').pwd,password);
assert.equal(collections.size,18); assert.equal(users.size,5); assert.equal(roles.size,4); assert.equal(adminRoles.size,1);
function clean(x) {if(Array.isArray(x))return x.map(clean); if(x&&typeof x==='object')return Object.fromEntries(Object.entries(x).filter(([k,v])=>!(k==='required'&&Array.isArray(v)&&!v.length)).map(([k,v])=>[k,clean(v)]));return x;}
for(const e of Object.values(model.collections)) {
 const actual=collections.get(e.ns.slice(7));
 assert.equal(actual.validationAction,'error');
 assert.deepEqual(JSON.parse(JSON.stringify(actual.validator.$jsonSchema)),clean(e.jsonSchema));
}
assert.equal(collections.get('cases').validationAction,'warn');
for(const role of roles.values())for(const p of role.privileges)
 assert(!p.actions.some(x=>/remove|drop|delete|bypass/i.test(x)));
assert.equal(roles.get('ingest_append').privileges[0].resource.collection,'cases');
assert.deepEqual([...roles.get('gis_guest').privileges].map(x=>x.resource.collection).filter(x=>['Social_group','Street','Building','Placement'].includes(x)),[]);
assert.equal(adminRoles.get('gis_admin').roles[0].role,'root');
console.log('PASS: 18 collections, source validators preserved, roles, repeat initialization. Mock only.');
