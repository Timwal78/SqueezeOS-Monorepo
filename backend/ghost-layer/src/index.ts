/**
 * Ghost Layer Sovereign — Backend API
 * Express server: ZK proof verification, fee estimates, XRPL relay
 *
 * Privacy rules:
 *   - All logs pass through scrubWalletAddress()
 *   - No trade data stored in cleartext
 *   - Treasury address only read from process.env
 */

import 'dotenv/config'
import express, { Request, Response, NextFunction } from 'express'
import cors from 'cors'
import helmet from 'helmet'
import { Client } from 'xrpl'
import { logger } from './logger'
import { feeRouter } from './routes/fee'
import { proofRouter } from './routes/proof'
import { statusRouter } from './routes/status'

const app = express()
const PORT = Number(process.env.API_PORT ?? 4000)

/* ── Middleware ──────────────────────────────────────────── */
app.use(helmet())
app.use(cors({ origin: process.env.NEXT_PUBLIC_API_URL ?? '*' }))
app.use(express.json({ limit: '1mb' }))

/* Request logger — scrubbed of wallet addresses */
app.use((req: Request, _res: Response, next: NextFunction) => {
  logger.info(`${req.method} ${req.path}`)
  next()
})

/* ── Routes ──────────────────────────────────────────────── */
app.use('/api/fee',    feeRouter)
app.use('/api/proof',  proofRouter)
app.use('/api/status', statusRouter)

app.get('/health', (_req, res) => {
  res.json({ status: 'ok', version: '1.0.0', module: 'Ghost Layer Backend' })
})

/* ── Error handler ───────────────────────────────────────── */
app.use((err: Error, _req: Request, res: Response, _next: NextFunction) => {
  logger.error(`Unhandled error: ${err.message}`)
  res.status(500).json({ error: 'Internal server error' })
})

/* ── XRPL Connection ─────────────────────────────────────── */
let xrplClient: Client | null = null

async function connectXRPL(): Promise<void> {
  const url = process.env.XRPL_NODE_URL ?? 'wss://xrplcluster.com'
  xrplClient = new Client(url)
  await xrplClient.connect()
  logger.info(`XRPL node connected: ${url}`)
}

/* ── Bootstrap ───────────────────────────────────────────── */
async function bootstrap() {
  /* Validate required env vars */
  if (!process.env.TREASURY_ADDRESS) {
    logger.warn('TREASURY_ADDRESS not set — Ghost Tax routing disabled')
  }

  /* Connect to XRPL in background (non-blocking startup) */
  connectXRPL().catch(err => {
    logger.warn(`XRPL connect failed, will retry: ${err.message}`)
  })

  app.listen(PORT, '0.0.0.0', () => {
    logger.info(`Ghost Layer API running on port ${PORT}`)
  })
}

bootstrap()

export { xrplClient }
