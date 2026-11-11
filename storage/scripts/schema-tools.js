// Shared pure helpers. Loaded by schema, indexes and verify in mongosh.
function normalizeSchema(value) {
  if (Array.isArray(value)) return value.map(normalizeSchema);
  if (value && typeof value === 'object') {
    return Object.fromEntries(Object.entries(value)
      .filter(([key, item]) => !(key === 'required' && Array.isArray(item) && !item.length))
      .map(([key, item]) => [key, normalizeSchema(item)]));
  }
  return value;
}
function canonical(value) {
  return JSON.stringify(value, (key, item) => item && !Array.isArray(item) && typeof item === 'object'
    ? Object.fromEntries(Object.keys(item).sort().map(k => [k, item[k]])) : item);
}
function casesOptions() {
  return {validator: {$jsonSchema: {bsonType: 'object', properties: {
    imported_at: {bsonType: 'date'}, source: {bsonType: 'string'}
  }}}, validationLevel: 'strict', validationAction: 'warn'};
}
function expectedIndexes(spec) {
  const result = [
    {collection: 'cases', key: {imported_at: 1}},
    {collection: 'cases', key: {source: 1, imported_at: 1}},
    {collection: 'Instances', key: {date: 1}}
  ];
  for (const entry of Object.values(spec.collections)) {
    result.push({collection: entry.ns.slice(7), key: {_owner_id: 1, _id: 1}});
    function visit(object, prefix = '') {
      for (const [field, def] of Object.entries(object.properties || {})) {
        const path = prefix + field;
        const types = Array.isArray(def.bsonType) ? def.bsonType : [def.bsonType];
        if (field !== '_id' && types.includes('objectId'))
          result.push({collection: entry.ns.slice(7), key: {[path]: 1}});
        if (def.properties) visit(def, path + '.');
      }
    }
    visit(entry.jsonSchema);
  }
  return result;
}
function indexMatches(actual, expected) {
  // Compound index field order is significant; never alphabetically sort its keys.
  return JSON.stringify(Object.entries(actual.key)) === JSON.stringify(Object.entries(expected)) &&
    !actual.hidden && !actual.sparse && !actual.partialFilterExpression && !actual.unique &&
    (!actual.collation || actual.collation.locale === 'simple');
}
function privilegeSignature(privileges) {
  const merged = new Map();
  for (const p of privileges || []) {
    const key = canonical(p.resource);
    if (!merged.has(key)) merged.set(key, new Set());
    for (const action of p.actions) merged.get(key).add(action);
  }
  return JSON.stringify([...merged].map(([resource, actions]) => [resource, [...actions].sort()])
    .sort(([a], [b]) => a.localeCompare(b)));
}
function rolesSignature(roles) {
  return JSON.stringify((roles || []).map(r => r.db + '.' + r.role).sort());
}
