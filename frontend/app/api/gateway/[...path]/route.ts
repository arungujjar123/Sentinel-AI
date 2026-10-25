// Server-side proxy for every /v1/* and /health* call the dashboard makes.
//
// The dashboard (a 'use client' component) never talks to the backend
// directly and never holds an API key — it calls same-origin
// /api/gateway/<path>, and this route handler (which runs server-side,
// never shipped to the browser) forwards the request to the real backend
// with the Authorization header injected here. This is what keeps
// SENTINEL_API_KEY out of the browser's network tab and JS bundle.
import { NextRequest, NextResponse } from 'next/server'

const BACKEND_URL = process.env.BACKEND_INTERNAL_URL || 'http://localhost:8000'
const API_KEY = process.env.SENTINEL_API_KEY || ''

// The key this proxy injects is the MASTER key, so an unrestricted
// passthrough would expose every admin endpoint — including POST and
// DELETE /v1/keys — to anyone who can load the dashboard. The dashboard
// itself has no login, so the allowlist below is what bounds that: only
// the read-only observability endpoints the dashboard actually polls,
// each pinned to the methods it uses. Everything else is rejected here
// and never reaches the backend.
//
// Keep this in sync with the fetches in app/page.tsx.
const ALLOWED_ROUTES: Record<string, string[]> = {
  'v1/metrics':        ['GET'],
  'v1/logs':           ['GET'],
  'v1/pricing':        ['GET'],
  'v1/cache/stats':    ['GET'],
  'v1/circuit/states': ['GET'],
  'v1/worker/stats':   ['GET'],
  'v1/webhook/config': ['GET'],
  'health':            ['GET'],
  'health/live':       ['GET'],
  'health/ready':      ['GET'],
  // The dashboard's "run demo" button issues real chat requests.
  'v1/chat':           ['POST'],
}

function isAllowed(path: string[], method: string): boolean {
  const route = path.join('/')
  const methods = Object.prototype.hasOwnProperty.call(ALLOWED_ROUTES, route)
    ? ALLOWED_ROUTES[route]
    : undefined
  return methods !== undefined && methods.includes(method)
}

async function proxy(req: NextRequest, path: string[]): Promise<NextResponse> {
  if (!API_KEY) {
    return NextResponse.json(
      { error: 'SENTINEL_API_KEY is not configured on the dashboard server' },
      { status: 500 },
    )
  }

  if (!isAllowed(path, req.method)) {
    return NextResponse.json(
      { error: 'Route not permitted through the dashboard proxy' },
      { status: 403 },
    )
  }

  const targetUrl = `${BACKEND_URL}/${path.join('/')}${req.nextUrl.search}`

  const headers = new Headers()
  headers.set('Authorization', `Bearer ${API_KEY}`)
  const contentType = req.headers.get('content-type')
  if (contentType) headers.set('Content-Type', contentType)

  const init: RequestInit = { method: req.method, headers, cache: 'no-store' }
  if (req.method !== 'GET' && req.method !== 'HEAD') {
    const body = await req.text()
    if (body) init.body = body
  }

  let backendRes: Response
  try {
    backendRes = await fetch(targetUrl, init)
  } catch (e) {
    return NextResponse.json({ error: `Backend unreachable: ${e}` }, { status: 502 })
  }

  const responseBody = await backendRes.text()
  return new NextResponse(responseBody, {
    status: backendRes.status,
    headers: { 'Content-Type': backendRes.headers.get('content-type') || 'application/json' },
  })
}

type RouteContext = { params: { path: string[] } }

export async function GET(req: NextRequest, { params }: RouteContext) {
  return proxy(req, params.path)
}

export async function POST(req: NextRequest, { params }: RouteContext) {
  return proxy(req, params.path)
}

export async function DELETE(req: NextRequest, { params }: RouteContext) {
  return proxy(req, params.path)
}

export async function PUT(req: NextRequest, { params }: RouteContext) {
  return proxy(req, params.path)
}
