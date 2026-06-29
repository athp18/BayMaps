import { FormEvent, useState, useEffect, useRef, useCallback } from 'react'

const NOMINATIM_URL = 'https://nominatim.openstreetmap.org/search'
const VIEWBOX = '-122.6,37.2,-121.5,38.1'

interface NominatimResult {
  display_name: string
  name?: string
}

interface SuggestionsState {
  items: NominatimResult[]
  visible: boolean
}

interface SearchBarProps {
  onSearch: (origin: string, dest: string) => void
  loading: boolean
}

function useSuggestions(query: string) {
  const [state, setState] = useState<SuggestionsState>({ items: [], visible: false })
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    if (timerRef.current) clearTimeout(timerRef.current)
    if (!query.trim() || query.length < 2) {
      setState({ items: [], visible: false })
      return
    }
    timerRef.current = setTimeout(async () => {
      try {
        const params = new URLSearchParams({
          q: query,
          format: 'json',
          limit: '5',
          viewbox: VIEWBOX,
          bounded: '0',
          'accept-language': 'en',
        })
        const res = await fetch(`${NOMINATIM_URL}?${params}`, {
          headers: { 'User-Agent': 'BayAreaPathfinder/1.0' },
        })
        const data: NominatimResult[] = await res.json()
        setState({ items: data, visible: data.length > 0 })
      } catch {
        setState({ items: [], visible: false })
      }
    }, 350)
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current)
    }
  }, [query])

  const hide = useCallback(() => setState(s => ({ ...s, visible: false })), [])

  return { suggestions: state.items, visible: state.visible, hide }
}

export function SearchBar({ onSearch, loading }: SearchBarProps) {
  const [origin, setOrigin] = useState('')
  const [dest, setDest] = useState('')

  const originSug = useSuggestions(origin)
  const destSug = useSuggestions(dest)

  const originWrapRef = useRef<HTMLDivElement>(null)
  const destWrapRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (originWrapRef.current && !originWrapRef.current.contains(e.target as Node)) {
        originSug.hide()
      }
      if (destWrapRef.current && !destWrapRef.current.contains(e.target as Node)) {
        destSug.hide()
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [originSug, destSug])

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (origin.trim() && dest.trim()) {
      onSearch(origin.trim(), dest.trim())
    }
  }

  function selectOrigin(result: NominatimResult) {
    setOrigin(result.name || result.display_name)
    originSug.hide()
  }

  function selectDest(result: NominatimResult) {
    setDest(result.name || result.display_name)
    destSug.hide()
  }

  return (
    <form onSubmit={handleSubmit} style={styles.form}>
      <div ref={originWrapRef} style={styles.inputWrap}>
        <input
          style={styles.input}
          type="text"
          placeholder="Origin (e.g. Ferry Building, SF)"
          value={origin}
          onChange={e => setOrigin(e.target.value)}
          onKeyDown={e => e.key === 'Escape' && originSug.hide()}
          disabled={loading}
          autoComplete="off"
        />
        {originSug.visible && (
          <ul style={styles.dropdown}>
            {originSug.suggestions.map((r, i) => (
              <li
                key={i}
                style={styles.dropdownItem}
                onMouseDown={() => selectOrigin(r)}
              >
                {r.display_name}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div ref={destWrapRef} style={styles.inputWrap}>
        <input
          style={styles.input}
          type="text"
          placeholder="Destination (e.g. SFO Airport)"
          value={dest}
          onChange={e => setDest(e.target.value)}
          onKeyDown={e => e.key === 'Escape' && destSug.hide()}
          disabled={loading}
          autoComplete="off"
        />
        {destSug.visible && (
          <ul style={styles.dropdown}>
            {destSug.suggestions.map((r, i) => (
              <li
                key={i}
                style={styles.dropdownItem}
                onMouseDown={() => selectDest(r)}
              >
                {r.display_name}
              </li>
            ))}
          </ul>
        )}
      </div>

      <button style={styles.button} type="submit" disabled={loading || !origin.trim() || !dest.trim()}>
        {loading ? 'Finding route…' : 'Find Route'}
      </button>
    </form>
  )
}

const styles: Record<string, React.CSSProperties> = {
  form: {
    display: 'flex',
    gap: 8,
    padding: '12px 16px',
    background: '#fff',
    borderBottom: '1px solid #e5e7eb',
    alignItems: 'center',
  },
  inputWrap: {
    flex: 1,
    position: 'relative',
  },
  input: {
    width: '100%',
    boxSizing: 'border-box',
    padding: '8px 12px',
    border: '1px solid #d1d5db',
    borderRadius: 6,
    fontSize: 14,
    outline: 'none',
  },
  button: {
    padding: '8px 20px',
    background: '#2563eb',
    color: '#fff',
    border: 'none',
    borderRadius: 6,
    fontSize: 14,
    cursor: 'pointer',
    whiteSpace: 'nowrap',
  },
  dropdown: {
    position: 'absolute',
    top: '100%',
    left: 0,
    right: 0,
    zIndex: 1000,
    margin: '2px 0 0 0',
    padding: 0,
    listStyle: 'none',
    background: '#fff',
    border: '1px solid #d1d5db',
    borderRadius: 6,
    boxShadow: '0 4px 12px rgba(0,0,0,0.12)',
    maxHeight: 220,
    overflowY: 'auto',
  },
  dropdownItem: {
    padding: '8px 12px',
    fontSize: 13,
    color: '#111827',
    cursor: 'pointer',
    borderBottom: '1px solid #f3f4f6',
  },
}
