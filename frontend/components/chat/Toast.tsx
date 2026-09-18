"use client";

export default function Toast({ message }: { message: string | null }) {
  return (
    <div
      className={`pointer-events-none fixed bottom-24 left-1/2 z-50 -translate-x-1/2 transition-all duration-200 ${
        message ? "translate-y-0 opacity-100" : "translate-y-2 opacity-0"
      }`}
    >
      <div className="glass glass-soft glass-edge rounded-full border border-transparent bg-[#2a2420] px-4 py-2 text-[12px] font-medium text-white shadow-lg dark:bg-white/10 dark:backdrop-blur-xl">
        {message}
      </div>
    </div>
  );
}
