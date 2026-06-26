/**
 * Fixed-position decorative math symbols and Lissajous curve for the login page.
 */
export function CornerDecorations() {
  return (
    <>
      {/* Corner math symbols */}
      <div className="font-mono" style={{ position: 'fixed', top: '-1rem', left: '1.5rem', color: 'rgba(253,176,34,0.06)', fontSize: '6rem', fontWeight: 300, pointerEvents: 'none', zIndex: 0, lineHeight: 1 }}>λ</div>
      <div className="font-mono" style={{ position: 'fixed', top: '-1rem', right: '1.5rem', color: 'rgba(253,176,34,0.06)', fontSize: '6rem', fontWeight: 300, pointerEvents: 'none', zIndex: 0, lineHeight: 1 }}>Σ</div>
      <div className="font-mono" style={{ position: 'fixed', bottom: '-1rem', left: '1.5rem', color: 'rgba(253,176,34,0.06)', fontSize: '6rem', fontWeight: 300, pointerEvents: 'none', zIndex: 0, lineHeight: 1 }}>∫</div>
      <div className="font-mono" style={{ position: 'fixed', bottom: '-1rem', right: '1.5rem', color: 'rgba(253,176,34,0.06)', fontSize: '6rem', fontWeight: 300, pointerEvents: 'none', zIndex: 0, lineHeight: 1 }}>∞</div>

      {/* Lissajous curve decoration */}
      <div style={{ position: 'fixed', top: '10%', right: '-5%', width: 500, height: 500, pointerEvents: 'none', zIndex: 0, opacity: 0.04 }}>
        <svg viewBox="0 0 200 200" xmlns="http://www.w3.org/2000/svg" style={{ width: '100%', height: '100%' }} aria-hidden="true">
          <path d="M 100 100 m -80 0 a 80 80 0 1 0 160 0 a 80 40 0 1 0 -160 0" fill="none" stroke="#FDB022" strokeWidth="0.3" opacity="0.5" />
          <path d="M 20,100 C 20,20 180,20 180,100 C 180,180 20,180 20,100" fill="none" stroke="#FDB022" strokeWidth="0.2" opacity="0.3" />
          <ellipse cx="100" cy="100" rx="70" ry="70" fill="none" stroke="#FDB022" strokeWidth="0.15" opacity="0.2" />
        </svg>
      </div>
    </>
  )
}
