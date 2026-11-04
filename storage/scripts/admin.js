(() => {
// Only administration commands load this; health does not inspect application users.
const connection = new Mongo('mongodb://127.0.0.1:27017/?serverSelectionTimeoutMS=3000&connectTimeoutMS=3000');
if (!connection.getDB('admin').auth(process.env.MONGO_INITDB_ROOT_USERNAME,process.env.MONGO_INITDB_ROOT_PASSWORD)) {
  print('FAIL admin authentication'); quit(1);
}
db = connection.getDB('Schema');

})();
