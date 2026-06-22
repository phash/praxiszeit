import { useState } from 'react'
import { Eye, EyeOff, AlertTriangle } from 'lucide-react'

interface PasswordInputProps extends Omit<React.InputHTMLAttributes<HTMLInputElement>, 'type'> {
  className?: string
  /**
   * Show a "Caps Lock is on" warning below the field while it has focus and
   * Caps Lock is active. Defaults to true — a wrong-case password is the most
   * common silent login failure. Set false where it would be noise.
   */
  showCapsLockWarning?: boolean
}

export default function PasswordInput({
  className = '',
  showCapsLockWarning = true,
  onKeyDown,
  onKeyUp,
  onBlur,
  ...props
}: PasswordInputProps) {
  const [visible, setVisible] = useState(false)
  const [capsLockOn, setCapsLockOn] = useState(false)

  // getModifierState is only meaningful on keyboard events, so we sync on both
  // keydown and keyup (keyup catches the CapsLock key press itself).
  const syncCapsLock = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (typeof e.getModifierState === 'function') {
      setCapsLockOn(e.getModifierState('CapsLock'))
    }
  }

  return (
    <div>
      <div className="relative">
        <input
          {...props}
          type={visible ? 'text' : 'password'}
          className={`${className} pr-10`}
          onKeyDown={(e) => { syncCapsLock(e); onKeyDown?.(e) }}
          onKeyUp={(e) => { syncCapsLock(e); onKeyUp?.(e) }}
          // We can no longer observe the modifier once focus leaves the field,
          // so clear the warning rather than show a stale one.
          onBlur={(e) => { setCapsLockOn(false); onBlur?.(e) }}
        />
        <button
          type="button"
          onClick={() => setVisible(v => !v)}
          className="absolute inset-y-0 right-0 flex items-center px-3 text-gray-400 hover:text-gray-600 focus:outline-hidden"
          tabIndex={-1}
          aria-label={visible ? 'Passwort verbergen' : 'Passwort anzeigen'}
        >
          {visible ? <EyeOff size={18} /> : <Eye size={18} />}
        </button>
      </div>
      {showCapsLockWarning && capsLockOn && (
        <p role="status" className="mt-1.5 flex items-center gap-1 text-xs text-amber-600">
          <AlertTriangle size={13} aria-hidden="true" />
          Feststelltaste (Caps&nbsp;Lock) ist aktiviert
        </p>
      )}
    </div>
  )
}
