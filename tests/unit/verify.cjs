// Regression harness executes actual init + verify scripts, not a reimplementation of verify.
const fs = require('node:fs'), path = require('node:path'), vm = require('node:vm');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '../..');
const spec = JSON.parse(fs.readFileSync(path.join(root, 'storage/schema/model.json'), 'utf8'));
function fixture() {
  const collections = new Map(), schemaRoles = new Map(), adminRoles = new Map(), users = new Map();
  const logs = [];
  function collection(name) {
    return {
      createIndex(key) { const list = collections.get(name).indexes; if (!list.some(i => JSON.stringify(i.key) === JSON.stringify(key))) list.push({key}); },
      getIndexes() { return collections.get(name).indexes; },
      findOne() { return null; }
    };
  }
  function roleDb(roles) {return {
    getRole(name, options = {}) {
      const role = roles.get(name);
      if (!role) return null;
      // Real MongoDB omits privileges unless explicitly requested.
      return options.showPrivileges ? role : {role: name, roles: role.roles};
    },
    createRole(role) {roles.set(role.role, role);},
    updateRole(name, role) {roles.set(name, role);}
  };}
  const admin = {...roleDb(adminRoles), auth: () => true,
    runCommand: () => ({parsed: {security: {authorization: 'enabled'}}})};
  const database = {...roleDb(schemaRoles), auth: () => true,
    getCollectionNames: () => [...collections.keys()],
    getCollectionInfos: () => [...collections].map(([name, c]) => ({name, options: c.options})),
    createCollection(name, options) {collections.set(name, {options, indexes: [{key: {_id: 1}}]});},
    runCommand({collMod, ...options}) { collections.get(collMod).options = options; return {ok: 1}; },
    getCollection: collection, cases: {findOne: () => null},
    getUser: name => users.get(name), createUser: user => users.set(user.user, user),
    updateUser: (name, user) => users.set(name, {...users.get(name), ...user})
  };
  database.getSiblingDB = name => name === 'admin' ? admin : database;
  const context = vm.createContext({
    db: database, print: message => logs.push(message),
    quit: code => {throw new Error('EXIT:' + code);},
    process: {env: {MONGO_INITDB_ROOT_USERNAME: 'root', MONGO_INITDB_ROOT_PASSWORD: 'private',
      INGEST_PASSWORD: 'i', PROCESSOR_PASSWORD: 'p', READER_PASSWORD: 'r', USER_PASSWORD: 'u', GUEST_PASSWORD: 'g'}},
    require: name => {assert.equal(name, 'fs'); return {readFileSync: () => JSON.stringify(spec)};},
    Mongo: function () {this.getDB = database.getSiblingDB;}
  });
  context.load = file => {
    const relative = file.replace('/opt/storage/', 'storage/scripts/').replace('/opt/init/', 'storage/init/');
    vm.runInContext(fs.readFileSync(path.join(root, relative), 'utf8'), context);
  };
  context.load('/opt/init/bootstrap.js');
  function verify() {
    logs.length = 0;
    try {context.load('/opt/storage/verify.js'); return true;} catch (_) {return false;}
  }
  return {verify, collections, schemaRoles, users, logs};
}
let f = fixture(); assert(f.verify(), f.logs.join('\n'));
// Privileges/actions can be returned in a different order.
for (const role of f.schemaRoles.values()) {role.privileges.reverse(); for (const p of role.privileges) p.actions.reverse();}
assert(f.verify());
f = fixture(); f.schemaRoles.get('gis_guest').privileges.push({resource:{db:'Schema',collection:'Building'},actions:['find']});
assert(!f.verify()); assert(f.logs.at(-1).includes('role: Schema.gis_guest'));
f = fixture(); f.users.delete('guest'); assert(!f.verify()); assert(f.logs.at(-1).includes('user grants: Schema.guest'));
f = fixture(); f.collections.get('cases').indexes.find(i => 'source' in i.key).key = {imported_at:1,source:1};
assert(!f.verify()); assert(f.logs.at(-1).includes('index: cases'));
f = fixture(); f.collections.get('Patient').indexes.push({key:{age:1},expireAfterSeconds:60});
assert(!f.verify()); assert(f.logs.at(-1).includes('TTL: Patient'));
f = fixture(); f.collections.get('cases').options.validationAction = 'error'; assert(!f.verify());
f = fixture(); f.collections.get('cases').indexes.find(i => 'source' in i.key).hidden = true; assert(!f.verify());
f = fixture(); f.collections.set('Pdtient',{options:{},indexes:[]}); assert(!f.verify());
console.log('PASS actual verify: showPrivileges, reordered grants, forbidden grants, missing user, compound index order, TTL, validator, hidden index, legacy names; mock only');
