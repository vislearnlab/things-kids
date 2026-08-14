// MongoDB upsert helper — mirrors vislearnlab/hybrid-drawing-rating.
//
// Usage from server.ts:
//   Insert(payload.data, payload.data.participantID, 'participantID');
//
// Looks up a doc by `{ [primaryKeyLocation]: primaryKey }`, then $set's
// the rest of the document. Inserts if not found. Re-runs with the same
// participantID overwrite cleanly — useful for mid-session resumes.

import { MongoClient } from 'mongodb';
import assert from 'assert';
import 'dotenv/config';

const mongoURL: string = process.env.MONGO_URL;
const databaseName: string = process.env.DATABASE;
const collectionName: string = process.env.COLLECTION;

const Insert = async (
  document: object,
  primaryKey: string,
  primaryKeyLocation: string,
): Promise<void> => {
  try {
    const client = await MongoClient.connect(mongoURL);
    const collection = client.db(databaseName).collection(collectionName);
    const query: any = {};
    query[primaryKeyLocation] = primaryKey;

    const result = await collection.updateOne(
      query,                  // find by participantID
      { $set: document },     // overwrite with new payload
      { upsert: true },       // insert if not found
    );

    if (result.upsertedCount > 0) {
      console.log(`[mongo] inserted ${primaryKeyLocation}=${primaryKey}`);
    } else if (result.matchedCount > 0) {
      console.log(`[mongo] updated  ${primaryKeyLocation}=${primaryKey}`);
    }
    assert.strictEqual(true, result.acknowledged);
    await client.close();
  } catch (err) {
    console.error('[mongo] error:', err);
  }
};

export { Insert };
