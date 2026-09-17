/**
 * Ambient backdrop rendered only in dark mode.
 * Layers (back to front):
 *  1. soft vignette
 *  2. two slowly drifting colour glows
 *  3. two soft orbs (large top-right, smaller bottom-left) that drift almost imperceptibly
 *  4. faint vertical light streaks that drift sideways
 *  5. fine grain
 * Everything is `hidden` in light mode so it costs nothing there.
 */
export default function DarkBackdrop() {
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 hidden overflow-hidden dark:block">
      {/* 1. vignette */}
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_80%_60%_at_50%_30%,rgba(255,255,255,0.035),transparent_70%)]" />

      {/* 2. drifting glows */}
      <div className="absolute -left-40 -top-32 h-[36rem] w-[36rem] animate-float-a rounded-full bg-sawo/30 blur-[130px] will-change-transform" />
      <div className="absolute -right-32 top-[28%] h-[30rem] w-[30rem] animate-float-b rounded-full bg-amber-500/[0.14] blur-[140px] will-change-transform" />

      {/* 3. two ambient orbs that drift almost imperceptibly: a large one top-right, a smaller one bottom-left */}
      <Orb className="left-[84%] top-[10%] w-[min(58rem,120vw)]" />
      <Orb className="left-[12%] top-[92%] w-[min(34rem,80vw)] [animation-delay:-35s] [animation-direction:reverse]" />

      {/* 4. vertical light streaks */}
      <div className="night-streaks absolute inset-0 animate-streak-drift opacity-70 blur-[1px]" />

      {/* 5. grain */}
      <div className="night-noise absolute inset-0 opacity-[0.045]" />
    </div>
  );
}

/**
 * One soft orb. Positioned by its centre (left/top in className), the drift
 * keyframes keep it centred while nudging it a few % of its own size.
 */
function Orb({ className, dim = false }: { className: string; dim?: boolean }) {
  return (
    <div
      className={`absolute aspect-square -translate-x-1/2 -translate-y-1/2 animate-orb-drift will-change-transform ${dim ? "opacity-75" : ""} ${className}`}
    >
      {/* outer halo, breathing very gently */}
      <div className="absolute -inset-[18%] animate-orb-breathe rounded-full bg-[radial-gradient(circle,rgba(193,154,118,0.16)_0%,rgba(193,154,118,0.06)_38%,transparent_66%)] blur-3xl" />
      {/* body: a slow-turning, slightly off-centre warm fill so the light shifts across it without a hotspot */}
      <div className="absolute inset-[8%] animate-orb-turn rounded-full bg-[radial-gradient(circle_at_42%_40%,rgba(222,182,142,0.22)_0%,rgba(193,154,118,0.13)_32%,rgba(157,116,90,0.06)_56%,transparent_72%)] blur-2xl" />
    </div>
  );
}
