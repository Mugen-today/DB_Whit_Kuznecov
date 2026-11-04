// One complete entry point: no pasted fragments or implicit helper variables.
(() => {
  let stage = 'admin authentication';
  try {
    load('/opt/storage/admin.js');
    load('/opt/storage/schema-tools.js');
    load('/opt/storage/role-spec.js');
    if (db.getSiblingDB('admin').runCommand({getCmdLineOpts: 1}).parsed?.security?.authorization !== 'enabled')
      throw new Error('Authorization disabled');
    const spec = JSON.parse(require('fs').readFileSync('/opt/schema/model.json', 'utf8'));
    const actual = new Map(db.getCollectionInfos().map(c => [c.name, c]));
    if (['Pdtient', 'Setlement'].some(name => actual.has(name))) {
      stage = 'legacy names: run migrate-plan'; throw new Error('Legacy collections');
    }
    for (const entry of Object.values(spec.collections)) {
      const name = entry.ns.slice(7);
      stage = 'validator: ' + name;
      const options = actual.get(name)?.options;
      if (!options || canonical(options.validator?.$jsonSchema) !== canonical(normalizeSchema(entry.jsonSchema)) ||
          options.validationLevel !== 'strict' || options.validationAction !== 'error') throw new Error('Validator mismatch');
    }
    stage = 'cases validator';
    const expected = casesOptions(), options = actual.get('cases')?.options;
    if (!options || canonical(options.validator) !== canonical(expected.validator) ||
        options.validationLevel !== expected.validationLevel || options.validationAction !== expected.validationAction)
      throw new Error('Cases validator mismatch');
    for (const [name, definition] of Object.entries(roleSpec(spec))) {
      stage = 'role: ' + roleDatabase(name) + '.' + name;
      const role = db.getSiblingDB(roleDatabase(name)).getRole(name, {showPrivileges: true});
      if (!role || !Array.isArray(role.privileges) ||
          privilegeSignature(role.privileges) !== privilegeSignature(definition.privileges) ||
          rolesSignature(role.roles) !== rolesSignature(definition.roles)) throw new Error('Role mismatch');
    }
    for (const [user, , role] of accountSpec()) {
      stage = 'user grants: Schema.' + user;
      const account = db.getUser(user);
      if (!account || rolesSignature(account.roles) !== rolesSignature([{role, db: 'Schema'}]))
        throw new Error('Grant mismatch');
    }
    const indexes = new Map();
    for (const name of ['cases', ...Object.values(spec.collections).map(e => e.ns.slice(7))]) {
      stage = 'indexes / TTL: ' + name;
      const list = db.getCollection(name).getIndexes();
      if (list.some(i => i.expireAfterSeconds !== undefined)) throw new Error('TTL forbidden');
      indexes.set(name, list);
    }
    for (const item of expectedIndexes(spec)) {
      stage = 'index: ' + item.collection + ' ' + JSON.stringify(item.key);
      if (!indexes.get(item.collection).some(i => indexMatches(i, item.key))) throw new Error('Index missing or incompatible');
    }
    print('PASS required indexes and TTL restrictions');
    for (const [user, key] of accountSpec()) {
      stage = 'authentication/read: Schema.' + user;
      const connection = new Mongo('mongodb://127.0.0.1:27017/?serverSelectionTimeoutMS=3000&connectTimeoutMS=3000');
      if (!connection.getDB('Schema').auth(user, process.env[key])) throw new Error('Authentication failed');
      connection.getDB('Schema').cases.findOne({});
    }
    print('PASS model validators, cases, exact role grants, service authentication and read');
  } catch (error) {
    // Only a known stage and numeric code, never raw errors containing credentials/data.
    const code = Number.isInteger(error.code) ? '; MongoDB code=' + error.code : '';
    print('FAIL Storage readiness at: ' + stage + code);
    quit(1);
  }
})();
