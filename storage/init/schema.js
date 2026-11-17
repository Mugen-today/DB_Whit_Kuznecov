(() => {
  load('/opt/storage/schema-tools.js');
  const spec = JSON.parse(require('fs').readFileSync('/opt/schema/model.json', 'utf8'));
  const storage = db.getSiblingDB('Schema');
  const existing = new Set(storage.getCollectionNames());
  if (['Pdtient', 'Setlement'].some(name => existing.has(name)))
    throw new Error('Legacy names detected: run migrate-plan/migrate');
  function ensure(name, options) {
    if (existing.has(name)) {
      if (!storage.runCommand({collMod: name, ...options}).ok) throw new Error('collMod failed: ' + name);
    } else storage.createCollection(name, options);
  }
  for (const entry of Object.values(spec.collections)) {
    if (!entry.ns.startsWith('Schema.')) throw new Error('Unexpected namespace');
    ensure(entry.ns.slice(7), {validator: {$jsonSchema: normalizeSchema(entry.jsonSchema)},
      validationLevel: 'strict', validationAction: 'error'});
  }
  ensure('cases', casesOptions());
})();
