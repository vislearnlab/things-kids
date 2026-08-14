// Quick connectivity test: connect, ping, write a probe doc, read it back, delete it.
import { MongoClient } from 'mongodb';
import 'dotenv/config';

async function main() {
  const url = process.env.MONGO_URL!;
  const dbName = process.env.DATABASE!;
  const collName = process.env.COLLECTION!;
  const redacted = url.replace(/:\/\/([^:]+):[^@]+@/, '://$1:***@');
  console.log(`connecting to ${redacted}`);
  const client = await MongoClient.connect(url, { serverSelectionTimeoutMS: 8000 });
  try {
    await client.db('admin').command({ ping: 1 });
    console.log('ping ok');
    const coll = client.db(dbName).collection(collName);
    const probe = { participantID: '__probe__', _probe: true, ts: new Date() };
    await coll.updateOne({ participantID: probe.participantID }, { $set: probe }, { upsert: true });
    const round = await coll.findOne({ participantID: probe.participantID });
    console.log('round-trip doc:', round);
    await coll.deleteOne({ participantID: probe.participantID });
    console.log(`cleaned up ${dbName}.${collName} probe doc`);
  } finally {
    await client.close();
  }
}

main().catch((e) => {
  console.error('FAIL:', e.message || e);
  process.exit(1);
});
