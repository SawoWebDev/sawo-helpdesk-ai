/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  // /api/* is proxied by app/api/[...path]/route.ts instead of a rewrite, since
  // Next's built-in rewrite proxy drops long-running requests (RAG generation
  // calls can take well over a minute on CPU-bound Ollama hosts).
  async rewrites() {
    const backendUrl = process.env.BACKEND_INTERNAL_URL || "http://localhost:8000";
    return [
      {
        source: "/uploads/:path*",
        destination: `${backendUrl}/uploads/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
