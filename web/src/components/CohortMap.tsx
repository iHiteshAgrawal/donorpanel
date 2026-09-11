import { CircleMarker, MapContainer, Polyline, TileLayer, Tooltip } from 'react-leaflet'
import type { Donor, Patient } from '../types'

interface Props {
  patient: Patient | null
  donors: Donor[]
  cohortIds: string[]
}

export function CohortMap({ patient, donors, cohortIds }: Props) {
  const located = donors.filter((d) => d.lat !== null && d.lon !== null)
  const centre: [number, number] = patient?.lat && patient?.lon
    ? [patient.lat, patient.lon]
    : [11.0168, 76.9558]

  const inCohort = new Set(cohortIds)
  const zoom = inCohort.size > 0 ? 7 : 8

  return (
    <MapContainer
      key={`${centre[0]}-${centre[1]}`}
      center={centre}
      zoom={zoom}
      scrollWheelZoom={false}
      className="h-full w-full"
      zoomControl={false}
    >
      <TileLayer
        url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
        attribution="&copy; OpenStreetMap"
      />

      {patient?.lat && patient?.lon &&
        located
          .filter((d) => inCohort.has(d.donor_id))
          .map((d) => (
            <Polyline
              key={`line-${d.donor_id}`}
              positions={[[patient.lat!, patient.lon!], [d.lat!, d.lon!]]}
              pathOptions={{ color: '#539FE5', weight: 1, opacity: 0.35, dashArray: '4 6' }}
            />
          ))}

      {located.map((d) => {
        const chosen = inCohort.has(d.donor_id)
        return (
          <CircleMarker
            key={d.donor_id}
            center={[d.lat!, d.lon!]}
            radius={chosen ? 7 : 4}
            pathOptions={{
              color: chosen ? '#539FE5' : '#414D5C',
              fillColor: chosen ? '#539FE5' : '#1B232D',
              fillOpacity: chosen ? 0.85 : 0.5,
              weight: chosen ? 2 : 1,
            }}
          >
            <Tooltip direction="top" offset={[0, -6]} opacity={1}>
              <span className="font-mono text-[11px]">
                {d.name} · {d.blood_group} · {d.city}
              </span>
            </Tooltip>
          </CircleMarker>
        )
      })}

      {patient?.lat && patient?.lon && (
        <CircleMarker
          center={[patient.lat, patient.lon]}
          radius={9}
          pathOptions={{ color: '#29AD32', fillColor: '#29AD32', fillOpacity: 0.25, weight: 2 }}
        >
          <Tooltip direction="top" offset={[0, -8]} opacity={1} permanent>
            <span className="font-mono text-[11px]">{patient.name} · {patient.hospital}</span>
          </Tooltip>
        </CircleMarker>
      )}
    </MapContainer>
  )
}
