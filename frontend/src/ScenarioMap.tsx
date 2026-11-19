import { useEffect, useRef, useState } from 'react'
import L from 'leaflet'
import { severityColors } from './data'
import type { Assignment, Scenario } from './types'

interface ScenarioMapProps {
  scenario: Scenario
  assignments?: Assignment[]
  compact?: boolean
}

const emptyAssignments: Assignment[] = []

function popup(title: string, detail: string): HTMLElement {
  const container = document.createElement('div')
  container.className = 'map-popup'
  const heading = document.createElement('strong')
  heading.textContent = title
  const body = document.createElement('span')
  body.textContent = detail
  container.append(heading, body)
  return container
}

export function ScenarioMap({ scenario, assignments = emptyAssignments, compact = false }: ScenarioMapProps) {
  const element = useRef<HTMLDivElement>(null)
  const map = useRef<L.Map | null>(null)
  const content = useRef<L.LayerGroup | null>(null)
  const [tileError, setTileError] = useState(false)

  useEffect(() => {
    if (!element.current) return
    const instance = L.map(element.current, { zoomControl: false, scrollWheelZoom: false })
    map.current = instance
    L.control.zoom({ position: 'bottomright' }).addTo(instance)

    const tiles = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; OpenStreetMap contributors',
      maxZoom: 19,
    })
    tiles.on('tileerror', () => setTileError(true))
    tiles.addTo(instance)

    return () => {
      instance.remove()
      map.current = null
      content.current = null
    }
  }, [])

  useEffect(() => {
    const instance = map.current
    if (!instance) return
    content.current?.remove()
    const layer = L.layerGroup().addTo(instance)
    content.current = layer

    for (const assignment of assignments) {
      const base = scenario.bases.find((item) => item.id === assignment.baseId)
      const area = scenario.areas.find((item) => item.id === assignment.areaId)
      if (!base || !area || assignment.quantity <= 0) continue
      L.polyline([base.location, area.location], {
        color: '#2b817f',
        weight: Math.min(2 + assignment.quantity * 0.4, 6),
        opacity: 0.62,
        dashArray: '7 6',
      }).bindPopup(popup(`${base.name} → ${area.name}`, `${assignment.quantity} ambulances assigned`)).addTo(layer)
    }

    for (const area of scenario.areas) {
      const color = severityColors[area.severity]
      L.circleMarker(area.location, {
        radius: compact ? 9 : 12,
        color: '#ffffff',
        weight: 3,
        fillColor: color,
        fillOpacity: 1,
      }).bindPopup(popup(area.name, `${area.severity} severity · ${area.demand} ambulances needed`)).addTo(layer)
    }

    for (const base of scenario.bases) {
      L.marker(base.location, {
        icon: L.divIcon({
          className: 'base-marker',
          html: '<span aria-hidden="true">✚</span>',
          iconSize: [34, 34],
          iconAnchor: [17, 17],
        }),
      }).bindPopup(popup(base.name, `${base.quantity} ambulances available`)).addTo(layer)
    }

    const points = [...scenario.areas.map((area) => area.location), ...scenario.bases.map((base) => base.location)]
    if (points.length > 0) {
      instance.fitBounds(L.latLngBounds(points), { padding: [35, 35], maxZoom: 13 })
    } else {
      instance.setView([20.5937, 78.9629], 5)
    }
    window.setTimeout(() => instance.invalidateSize(), 0)
  }, [scenario, assignments, compact])

  return (
    <>
      <div className={`map-wrap ${compact ? 'map-wrap--compact' : ''}`}>
        <div className="map-canvas" ref={element} role="img" aria-label={`Map of ${scenario.name} areas and resource bases`} />
      </div>
      {tileError && (
        <section className="map-fallback" aria-label="Map location list">
          <p role="status">Map tiles unavailable. Area and base locations remain listed alongside the map.</p>
          <div className="map-fallback-lists">
            <div>
              <h3>Affected areas</h3>
              {scenario.areas.length ? (
                <ul>{scenario.areas.map((area) => (
                  <li key={area.id}><strong>{area.name}</strong><span>{area.severity} severity · {area.demand} needed</span></li>
                ))}</ul>
              ) : <p>No affected areas added.</p>}
            </div>
            <div>
              <h3>Resource bases</h3>
              {scenario.bases.length ? (
                <ul>{scenario.bases.map((base) => (
                  <li key={base.id}><strong>{base.name}</strong><span>{base.quantity} available</span></li>
                ))}</ul>
              ) : <p>No resource bases added.</p>}
            </div>
          </div>
        </section>
      )}
    </>
  )
}
