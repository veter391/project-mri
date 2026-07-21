// Diagnostic-instrument atmosphere: a fixed, non-interactive CRT scanline +
// vignette overlay. Pure CSS (see .mri-crt in globals.css); decorative.
export function Crt() {
  return <div aria-hidden="true" className="mri-crt" />;
}
