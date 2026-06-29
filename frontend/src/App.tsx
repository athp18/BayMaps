import { Map } from './components/Map'
import { RoutePanel } from './components/RoutePanel'
import { SearchBar } from './components/SearchBar'
import { useRoute } from './hooks/useRoute'
import { useTraffic } from './hooks/useTraffic'

export default function App() {
  const { route, loading, error, originCoord, destCoord, findRoute } = useRoute()
  useTraffic()

  return (
    <>
      <SearchBar onSearch={findRoute} loading={loading} />
      <RoutePanel route={route} loading={loading} error={error} />
      <Map route={route} originCoord={originCoord} destCoord={destCoord} />
    </>
  )
}
