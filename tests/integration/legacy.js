// Destructive fixture ONLY for a random disposable integration project.
(() => {
  if (process.env.ISOLATED_STORAGE_TEST !== '1') {print('REFUSED: isolated fixture only'); quit(1);}
  load('/opt/storage/admin.js');
  const patient = ObjectId('000000000000000000000001');
  const settlement = ObjectId('000000000000000000000002');
  const municipality = ObjectId('000000000000000000000003');
  const building = ObjectId('000000000000000000000004');
  if (process.env.FIXTURE_ACTION === 'seed') {
    db.Patient.renameCollection('Pdtient', false);
    db.Settlement.renameCollection('Setlement', false);
    db.Pdtient.insertOne({_id: patient, medical_record: {'сhronic_diseases': /test/i}});
    db.Setlement.insertOne({_id: settlement});
    db.Municipality.insertOne({_id: municipality, setlement: settlement});
    db.Building.insertOne({_id: building, courpus: NumberInt(0)});
    db.dropUser('guest');
    print('PASS disposable legacy fixture seeded');
  } else {
    if (db.getCollectionNames().some(n => ['Pdtient','Setlement'].includes(n))) throw Error('Legacy names remain');
    if (!db.Patient.findOne({_id: patient}).medical_record.chronic_diseases) throw Error('Nested field lost');
    if (!db.Municipality.findOne({_id: municipality}).settlement.equals(settlement)) throw Error('Reference changed');
    if (Number(db.Building.findOne({_id: building}).corpus) !== 0) throw Error('Zero value lost');
    if (!db.getUser('guest')) throw Error('Missing user not provisioned');
    print('PASS real migration preserves IDs, references and zero values; missing guest restored');
  }
})();
