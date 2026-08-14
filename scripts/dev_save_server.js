// Minimal local save sink for piloting, so /submit works without touching
// the lab MongoDB. Writes each submission to analysis/pilot_data/<id>.json.
//
// The Vite dev server already proxies /submit and /health to :9000, so just
// run this alongside `npm run dev`:
//
//     node scripts/dev_save_server.js
//
// This is for piloting only — production still uses src/server.ts + Mongo.

const express = require('express');
const fs = require('fs');
const path = require('path');

const PORT = process.env.PORT || 9000;
const OUT_DIR = path.join(__dirname, '..', 'analysis', 'pilot_data');
fs.mkdirSync(OUT_DIR, { recursive: true });

const app = express();
app.use(express.json({ limit: '20mb' }));

app.get('/health', (_req, res) => res.json({ ok: true, sink: OUT_DIR }));

app.post('/submit', (req, res) => {
  const { participantID, data } = req.body || {};
  if (!participantID) return res.status(400).json({ ok: false, error: 'missing participantID' });
  // Timestamped so repeated runs by the same pilot participant don't clobber.
  const stamp = new Date().toISOString().replace(/[:.]/g, '-');
  const file = path.join(OUT_DIR, `${participantID}_${stamp}.json`);
  fs.writeFileSync(file, JSON.stringify(data, null, 2));
  console.log(`saved ${data?.n_trials ?? '?'} trials -> ${path.basename(file)}`);
  res.json({ ok: true, file: path.basename(file) });
});

app.listen(PORT, () => console.log(`dev save sink on :${PORT} -> ${OUT_DIR}`));
