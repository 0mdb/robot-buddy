import type {
  CellStyle,
  CellValueChangedEvent,
  ColDef,
  ICellRendererParams,
} from 'ag-grid-community'
import { AllCommunityModule, ModuleRegistry } from 'ag-grid-community'
import { AgGridReact } from 'ag-grid-react'
import { useCallback, useMemo, useRef, useState } from 'react'
import 'ag-grid-community/styles/ag-theme-alpine.css'
import { useParamsList, useUpdateParams } from '../hooks/useParams'
import { debounce } from '../lib/debounce'
import styles from '../styles/global.module.css'
import type { ParamDef } from '../types'

ModuleRegistry.registerModules([AllCommunityModule])

// ---------------------------------------------------------------------------
// Badge renderers
// ---------------------------------------------------------------------------

function MutableRenderer(params: ICellRendererParams) {
  const val = params.value as string
  if (val === 'runtime') {
    return <span className={`${styles.badge} ${styles.badgeBlue}`}>{val}</span>
  }
  return <span className={`${styles.badge} ${styles.badgeDim}`}>{val}</span>
}

function SafetyRenderer(params: ICellRendererParams) {
  const val = params.value as string
  if (val === 'safe') {
    return <span className={`${styles.badge} ${styles.badgeGreen}`}>{val}</span>
  }
  return <span className={`${styles.badge} ${styles.badgeRed}`}>{val}</span>
}

// ---------------------------------------------------------------------------
// Main Tab
// ---------------------------------------------------------------------------

export default function ParamsTab() {
  const { data: params, isLoading } = useParamsList()
  const updateParams = useUpdateParams()
  const [search, setSearch] = useState('')

  // Debounced param update
  const debouncedUpdate = useRef(
    debounce((name: string, value: number) => {
      updateParams.mutate({ [name]: value })
    }, 150),
  ).current

  const onCellValueChanged = useCallback(
    (event: CellValueChangedEvent) => {
      const row = event.data as ParamDef
      const newValue = Number(event.newValue)
      if (!Number.isNaN(newValue)) {
        debouncedUpdate(row.name, newValue)
      }
    },
    [debouncedUpdate],
  )

  const columnDefs = useMemo<ColDef[]>(
    () => [
      {
        field: 'name',
        headerName: 'Name',
        flex: 2,
        filter: true,
        rowGroup: false,
      },
      {
        field: 'value',
        headerName: 'Value',
        flex: 1,
        editable: true,
        cellEditor: 'agNumberCellEditor',
        cellStyle: { fontFamily: 'var(--font-mono)', fontWeight: 600 } as CellStyle,
      },
      {
        field: 'default',
        headerName: 'Default',
        flex: 1,
        cellStyle: { color: '#888' } as CellStyle,
      },
      {
        field: 'min',
        headerName: 'Min',
        flex: 0.7,
        cellStyle: { color: '#888' } as CellStyle,
      },
      {
        field: 'max',
        headerName: 'Max',
        flex: 0.7,
        cellStyle: { color: '#888' } as CellStyle,
      },
      {
        field: 'owner',
        headerName: 'Owner',
        flex: 1,
        rowGroup: true,
        hide: true,
      },
      {
        field: 'mutable',
        headerName: 'Mutable',
        flex: 1,
        cellRenderer: MutableRenderer,
      },
      {
        field: 'safety',
        headerName: 'Safety',
        flex: 1,
        cellRenderer: SafetyRenderer,
      },
      {
        field: 'doc',
        headerName: 'Doc',
        flex: 3,
        cellStyle: { color: '#aaa', fontSize: 12 } as CellStyle,
      },
    ],
    [],
  )

  const defaultColDef = useMemo<ColDef>(
    () => ({
      sortable: true,
      resizable: true,
    }),
    [],
  )

  if (isLoading) {
    return <div style={{ padding: 16, color: '#888' }}>Loading parameters...</div>
  }

  return (
    <div style={{ padding: 16, display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* Search box */}
      <div style={{ marginBottom: 12 }}>
        <input
          type="text"
          placeholder="Search parameters..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{ width: 320, padding: '6px 10px' }}
        />
      </div>

      {/* AG Grid */}
      <div className="ag-theme-alpine-dark" style={{ flex: 1, minHeight: 0 }}>
        <AgGridReact
          rowData={params}
          columnDefs={columnDefs}
          defaultColDef={defaultColDef}
          quickFilterText={search}
          onCellValueChanged={onCellValueChanged}
          groupDefaultExpanded={1}
          animateRows={false}
          domLayout="normal"
          getRowId={(p) => p.data?.name}
        />
      </div>
    </div>
  )
}
