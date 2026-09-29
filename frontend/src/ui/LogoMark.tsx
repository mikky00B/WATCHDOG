type LogoMarkProps = {
  size?: number;
  /** Render in a single color that inherits from text color (emails, dark chips). */
  mono?: boolean;
  title?: string;
};

/**
 * WATCHDOG brand mark: eartipped W with a teal pulse peak.
 * Vector recreation of the founder's mark-512.png (see logobyme/ and logo-fit.html).
 */
export function LogoMark({ size = 24, mono = false, title }: LogoMarkProps) {
  const blue = mono ? "currentColor" : "#2563eb";
  const teal = mono ? "currentColor" : "#0d9488";
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 512 512"
      role={title ? "img" : undefined}
      aria-label={title}
      aria-hidden={title ? undefined : true}
      focusable="false"
    >
      <path
        d="M 148 452 L 240 232 Q 256 198 272 232 L 364 452"
        fill="none"
        stroke={teal}
        strokeWidth={62}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        fill={blue}
        d="M 117 466 C 114 384 111 300 108 232 C 107 216 106 204 104 196 C 92 174 74 148 58 122 C 46 104 36 82 27 60 C 45 84 67 104 89 126 C 112 150 137 176 149 208 C 164 244 174 300 176 380 C 177 420 178 442 179 464 A 33 33 0 0 1 117 466 Z"
      />
      <path
        fill={blue}
        d="M 395 466 C 398 384 401 300 404 232 C 405 216 406 204 408 196 C 420 174 438 148 454 122 C 466 104 476 82 485 60 C 467 84 445 104 423 126 C 400 150 375 176 363 208 C 348 244 338 300 336 380 C 335 420 334 442 333 464 A 33 33 0 0 0 395 466 Z"
      />
    </svg>
  );
}
