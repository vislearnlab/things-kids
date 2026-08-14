// Express + MongoDB save server — mirrors vislearnlab/hybrid-drawing-rating.
//
// In production: build the frontend with `vite build` (writes to dist/),
// then run this with `ts-node src/server.ts`. The server serves dist/
// statically AND exposes POST /submit which upserts the payload into
// the lab MongoDB cluster.
//
// In dev: run `npm run dev` for the frontend (vite hot reload) and this
// server in a separate terminal for /submit. Or skip /submit entirely
// during dev — the client's thank-you page falls back to a download
// button if the POST fails.

import express, { Request, Response } from 'express';
import cors from 'cors';
import path from 'path';
import fs from 'fs';
import https from 'https';
import http from 'http';
import 'dotenv/config';
import { Insert } from './mongo';

const app = express();
const PORT = process.env.PORT || 9000;

// BASE_PATH: set in .env when running behind nginx with a path prefix.
// Leave unset for local development; the app is served at /.
const prefix = process.env.BASE_PATH ? `/${process.env.BASE_PATH}` : '';

app.use(cors());
app.use(express.urlencoded({ extended: true }));
app.use(express.json({ limit: '20mb' }));

// Serve the built frontend (Vite output) from dist/.
app.use(prefix || '/', express.static(path.join(__dirname, '..', 'dist')));

// When a prefix is set, redirect bare / to the prefixed URL.
if (prefix) {
  app.get('/', (_req: Request, res: Response) => res.redirect(prefix + '/'));
}

// Save participant data — upsert on participantID.
app.post(`${prefix}/submit`, async (req: Request, res: Response) => {
  try {
    const payload = req.body;
    if (!payload?.participantID) {
      return res.status(400).json({ ok: false, error: 'missing participantID' });
    }
    await Insert(payload.data, payload.participantID, 'participantID');
    res.json({ ok: true });
  } catch (err) {
    console.error('[submit] error', err);
    res.status(500).json({ ok: false, error: String(err) });
  }
});

app.get(`${prefix}/health`, (_req: Request, res: Response) => {
  res.json({ ok: true, env: process.env.ENVIRONMENT || 'dev' });
});

// Use HTTPS in production (set ENVIRONMENT=production and point
// CREDENTIALS_PATH to a folder with ssl_key.pem and ssl_cert.pem).
let server: http.Server | https.Server;
if (process.env.ENVIRONMENT === 'production') {
  const credentials = process.env.CREDENTIALS_PATH || 'credentials/';
  const options = {
    key: fs.readFileSync(`${credentials}ssl_key.pem`),
    cert: fs.readFileSync(`${credentials}ssl_cert.pem`),
  };
  server = https.createServer(options, app);
} else {
  server = http.createServer(app);
}

server.listen(PORT, () => {
  console.log(`[mochi-kids] server running on port ${PORT}${prefix ? ` (prefix ${prefix})` : ''}`);
});
