"use client";

import ReactMarkdown from "react-markdown";

export interface ChatMessage {
  role: "user" | "assistant";
  text: string;
  isFallback?: boolean;
  imageUrls?: string[];
  referenceUrls?: string[];
}

export default function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[80%] rounded-2xl px-4 py-3 text-sm shadow-sm ${
          isUser
            ? "bg-blue-600 text-white"
            : message.isFallback
              ? "bg-amber-50 text-amber-900 border border-amber-200"
              : "bg-white text-slate-800 border border-slate-200"
        }`}
      >
        <div className="prose prose-sm max-w-none prose-p:my-1">
          <ReactMarkdown>{message.text}</ReactMarkdown>
        </div>

        {message.imageUrls && message.imageUrls.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-2">
            {message.imageUrls.map((url) => (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                key={url}
                src={url}
                alt="Reference"
                className="max-h-40 rounded-lg border border-slate-200 object-cover"
              />
            ))}
          </div>
        )}

        {message.referenceUrls && message.referenceUrls.length > 0 && (
          <div className="mt-2 flex flex-col gap-1">
            {message.referenceUrls.map((url) => (
              <a
                key={url}
                href={url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-blue-600 underline text-xs break-all"
              >
                {url}
              </a>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
