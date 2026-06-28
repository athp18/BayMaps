import { FormEvent, useState } from 'react'

interface SearchBarProps {
  onSearch: (origin: string, dest: string) => void
  loading: boolean
}

export function SearchBar({ onSearch, loading }: SearchBarProps) {
  const [origin, setOrigin] = useState('')
  const [dest, setDest] = useState('')

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (origin.trim() && dest.trim()) {
      onSearch(origin.trim(), dest.trim())
    }
  }

  return (
    <form onSubmit={handleSubmit} style={styles.form}>
      <input
        style={styles.input}
        type="text"
        placeholder="Origin (e.g. Ferry Building, SF)"
        value={origin}
        onChange={e => setOrigin(e.target.value)}
        disabled={loading}
      />
      <input
        style={styles.input}
        type="text"
        placeholder="Destination (e.g. SFO Airport)"
        value={dest}
        onChange={e => setDest(e.target.value)}
        disabled={loading}
      />
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
  input: {
    flex: 1,
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
}
