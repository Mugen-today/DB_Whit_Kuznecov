(() => {
  load('/opt/storage/schema-tools.js');
  const spec = JSON.parse(require('fs').readFileSync('/opt/schema/model.json', 'utf8'));
  const storage = db.getSiblingDB('Schema');
  for (const index of expectedIndexes(spec))
    storage.getCollection(index.collection).createIndex(index.key);
})();
