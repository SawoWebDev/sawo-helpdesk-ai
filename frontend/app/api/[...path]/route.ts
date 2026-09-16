import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";
export const maxDuration = 300;

const BACKEND_URL = process.env.BACKEND_INTERNAL_URL || "http://localhost:8000";

const HOP_BY_HOP_HEADERS = new Set([
  "connection",
  "keep-alive",
  "transfer-encoding",
  "content-encoding",
  "content-length",
  "host",
]);

async function proxy(req: NextRequest, params: { path: string[] }) {
  const targetUrl = `${BACKEND_URL}/api/${params.path.join("/")}${req.nextUrl.search}`;

  const headers = new Headers();
  req.headers.forEach((value, key) => {
    if (!HOP_BY_HOP_HEADERS.has(key.toLowerCase())) headers.set(key, value);
  });
  // Best-effort visitor IP for the backend's chat-log grouping. There's no
  // reverse proxy in front of this app, so req.ip (populated on platforms
  // like Vercel) may be undefined when self-hosted — the backend already
  // falls back to its own connection's address if this header is absent.
  if (!headers.has("x-forwarded-for") && req.ip) {
    headers.set("x-forwarded-for", req.ip);
  }

  const hasBody = !["GET", "HEAD"].includes(req.method);

  const res = await fetch(targetUrl, {
    method: req.method,
    headers,
    body: hasBody ? await req.arrayBuffer() : undefined,
    redirect: "manual",
    // @ts-expect-error Node's undici fetch respects this to disable its own timeout
    duplex: hasBody ? "half" : undefined,
  });

  const responseHeaders = new Headers();
  res.headers.forEach((value, key) => {
    if (!HOP_BY_HOP_HEADERS.has(key.toLowerCase())) responseHeaders.set(key, value);
  });

  return new NextResponse(res.body, {
    status: res.status,
    statusText: res.statusText,
    headers: responseHeaders,
  });
}

export async function GET(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  return proxy(req, await ctx.params);
}
export async function POST(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  return proxy(req, await ctx.params);
}
export async function PUT(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  return proxy(req, await ctx.params);
}
export async function DELETE(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  return proxy(req, await ctx.params);
}
export async function PATCH(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  return proxy(req, await ctx.params);
}
