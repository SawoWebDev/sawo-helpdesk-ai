import { ApiError } from "@/lib/api";

/** POSTs to a server-sent-events endpoint (POST /api/chat/stream): calls
 *  onDelta for each `delta` event's text and resolves with the `done`
 *  event's payload. Rejects on an HTTP error, an `error` event, or a stream
 *  that ends without `done`. */
export async function streamChat<T>(
  body: unknown,
  onDelta: (text: string) => void
): Promise<T> {
  const res = await fetch("/api/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify(body),
  });
  if (!res.ok || !res.body) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      // non-JSON error body
    }
    throw new ApiError(res.status, String(detail));
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let boundary: number;
    while ((boundary = buffer.indexOf("\n\n")) !== -1) {
      const block = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      let event = "message";
      let data = "";
      for (const line of block.split("\n")) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) data += line.slice(5).trim();
      }
      if (!data) continue;
      const payload = JSON.parse(data);
      if (event === "delta") onDelta(payload.text);
      else if (event === "done") {
        reader.cancel().catch(() => {});
        return payload as T;
      } else if (event === "error") throw new ApiError(500, payload.detail ?? "Stream error");
    }
  }
  throw new ApiError(500, "Answer stream ended unexpectedly");
}
