function base(children: React.ReactNode) {
  return (
    <svg viewBox="0 0 24 24" className="h-full w-full" fill="currentColor">
      {children}
    </svg>
  );
}

export function SalesIcon() {
  return base(
    <>
      <rect x="3.5" y="13" width="4" height="7.5" rx="1.2" />
      <rect x="10" y="9" width="4" height="11.5" rx="1.2" />
      <rect x="16.5" y="4.5" width="4" height="16" rx="1.2" />
    </>
  );
}

export function MarketingIcon() {
  return base(
    <>
      <path d="M4.5 9h7.2v6H4.5A1.5 1.5 0 0 1 3 13.5v-3A1.5 1.5 0 0 1 4.5 9Z" />
      <path d="M13 8.6 19.4 3.9a1 1 0 0 1 1.6.8v14.6a1 1 0 0 1-1.6.8L13 15.4V8.6Z" />
      <path d="M5.6 16.5h3.1l.85 3.5a1.1 1.1 0 0 1-1.07 1.36h-.66a1.1 1.1 0 0 1-1.07-.85L5.6 16.5Z" />
    </>
  );
}

export function HrIcon() {
  return base(
    <>
      <circle cx="12" cy="7.8" r="3.8" />
      <path d="M4 19.4c0-3.9 3.6-6.6 8-6.6s8 2.7 8 6.6a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1Z" />
    </>
  );
}

export function ItIcon() {
  return base(
    <>
      <path d="M3 5.4A1.6 1.6 0 0 1 4.6 3.8h14.8A1.6 1.6 0 0 1 21 5.4v9.4a1.6 1.6 0 0 1-1.6 1.6H4.6A1.6 1.6 0 0 1 3 14.8V5.4Z" />
      <path d="M9.6 18h4.8l.5 2h-5.8l.5-2Z" />
      <rect x="6.8" y="19.6" width="10.4" height="1.8" rx="0.9" />
    </>
  );
}

export function ProductIcon() {
  return base(
    <>
      <path d="M12 2.6 20.8 7 12 11.4 3.2 7 12 2.6Z" />
      <path d="M3 8.9v8.2l8.2 4.1v-8.2L3 8.9Z" fillOpacity="0.8" />
      <path d="M21 8.9v8.2l-8.2 4.1v-8.2L21 8.9Z" fillOpacity="0.55" />
    </>
  );
}

export function ProcessesIcon() {
  return base(
    <>
      <circle cx="12" cy="12" r="5" fill="none" stroke="currentColor" strokeWidth="3.4" />
      {[0, 45, 90, 135, 180, 225, 270, 315].map((deg) => (
        <rect
          key={deg}
          x="10.9"
          y="2.6"
          width="2.2"
          height="4.4"
          rx="0.8"
          transform={`rotate(${deg} 12 12)`}
        />
      ))}
    </>
  );
}
