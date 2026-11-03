import { useMemo, useRef, useState } from 'react'
import {
  Camera,
  ChevronDown,
  ChevronUp,
  Download,
  FileImage,
  FileText,
  HardDrive,
  Moon,
  Music4,
  PlayCircle,
  Save,
  Settings2,
  ShieldCheck,
  SunMedium,
  UploadCloud,
} from 'lucide-react'
import './App.css'

type ThemeMode = 'dark' | 'light'

type MetadataResponse = {
  fileName: string
  mediaType: string
  tooling: { exiftool: boolean; ffprobe: boolean }
  fileInfo: Record<string, string>
  details: Record<string, string>
  editableFields: Record<string, string>
  downloadUrl?: string
}

const initialMetadata: Record<string, string> = {
  Title: '',
  Description: '',
  Author: '',
  Creator: '',
  Copyright: '',
  Software: '',
  Comment: '',
  Artist: '',
  Album: '',
  Genre: '',
  TrackNumber: '',
  DiscNumber: '',
  Year: '',
}

function App() {
  const inputRef = useRef<HTMLInputElement | null>(null)
  const [theme, setTheme] = useState<ThemeMode>('dark')
  const [loading, setLoading] = useState(false)
  const [status, setStatus] = useState('Ready for a media file')
  const [error, setError] = useState<string | null>(null)
  const [currentFile, setCurrentFile] = useState<string>('')
  const [downloadUrl, setDownloadUrl] = useState('')
  const [fileInfo, setFileInfo] = useState<Record<string, string>>({})
  const [details, setDetails] = useState<Record<string, string>>({})
  const [editableFields, setEditableFields] = useState<Record<string, string>>(initialMetadata)
  const [mediaType, setMediaType] = useState('unknown')
  const [expanded, setExpanded] = useState({
    file: true,
    metadata: true,
    tags: true,
  })

  const supportedFormats = useMemo(
    () => ['JPEG', 'PNG', 'WEBP', 'TIFF', 'HEIC', 'MP4', 'MOV', 'MKV', 'AVI', 'WEBM', 'MP3', 'M4A', 'FLAC', 'WAV', 'OGG'],
    [],
  )

  const handleThemeToggle = () => {
    setTheme((value) => (value === 'dark' ? 'light' : 'dark'))
  }

  const handleFileSelection = async (file: File) => {
    try {
      setLoading(true)
      setError(null)
      setStatus(`Preparing ${file.name}...`)

      const formData = new FormData()
      formData.append('file', file)

      const response = await fetch('/api/metadata', {
        method: 'POST',
        body: formData,
      })

      if (!response.ok) {
        const payload = await response.json().catch(() => ({}))
        throw new Error(payload.detail || 'Unable to read metadata for this file.')
      }

      const data: MetadataResponse = await response.json()
      setCurrentFile(data.fileName)
      setFileInfo(data.fileInfo)
      setDetails(data.details)
      setEditableFields({ ...initialMetadata, ...data.editableFields })
      setMediaType(data.mediaType)
      setDownloadUrl(data.downloadUrl || '')
      setStatus(`Loaded ${data.fileName} using safe metadata-only updates.`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unexpected upload error.')
      setStatus('Metadata read failed')
    } finally {
      setLoading(false)
    }
  }

  const handleSubmit = async () => {
    if (!currentFile) {
      setError('Choose a media file before saving updates.')
      return
    }

    try {
      setLoading(true)
      setError(null)
      setStatus('Writing metadata without re-encoding streams...')

      const payload = new URLSearchParams({
        file_name: currentFile,
        updates: JSON.stringify(editableFields),
      })

      const response = await fetch('/api/update-metadata', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
        },
        body: payload,
      })

      if (!response.ok) {
        const data = await response.json().catch(() => ({}))
        throw new Error(data.detail || 'Unable to write metadata.')
      }

      const result = await response.json()
      setDownloadUrl(result.downloadUrl)
      setStatus('Metadata updated successfully. Media streams preserved.')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to save metadata.')
      setStatus('Save failed')
    } finally {
      setLoading(false)
    }
  }

  const onFileInput = (event: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = event.target.files?.[0]
    if (selectedFile) {
      void handleFileSelection(selectedFile)
    }
  }

  const onDrop = (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    const selectedFile = event.dataTransfer.files?.[0]
    if (selectedFile) {
      void handleFileSelection(selectedFile)
    }
  }

  const detailsEntries = Object.entries(details)
  const infoEntries = Object.entries(fileInfo)
  const editableEntries = Object.entries(editableFields)

  return (
    <div className={`app-shell ${theme}`}>
      <header className="topbar">
        <div className="brand-wrap">
          <div className="brand-mark">MM</div>
          <div>
            <p className="eyebrow">Metadata Toolkit</p>
            <h1>Media Metadata Editor</h1>
          </div>
        </div>

        <div className="topbar-actions">
          <button type="button" className="icon-button" aria-label="Open settings">
            <Settings2 size={18} />
          </button>
          <button type="button" className="icon-button" onClick={handleThemeToggle} aria-label="Toggle theme">
            {theme === 'dark' ? <SunMedium size={18} /> : <Moon size={18} />}
          </button>
        </div>
      </header>

      <main className="main-grid">
        <section className="panel upload-panel">
          <div className="panel-header">
            <h2>Upload media</h2>
            <span className="pill">{mediaType.toUpperCase()}</span>
          </div>

          <div className="dropzone" onDragOver={(event) => event.preventDefault()} onDrop={onDrop}>
            <UploadCloud size={42} className="drop-icon" />
            <p>Drop your media here</p>
            <button type="button" className="browse-button" onClick={() => inputRef.current?.click()}>
              Browse Files
            </button>
            <input ref={inputRef} type="file" hidden onChange={onFileInput} />
            <div className="supported-list">
              {supportedFormats.map((format) => (
                <span key={format}>{format}</span>
              ))}
            </div>
          </div>

          <div className="status-bar">
            <ShieldCheck size={16} />
            <span>{status}</span>
          </div>

          {error && <div className="error-banner">{error}</div>}
        </section>

        <section className="panel dashboard-panel">
          <div className="panel-header">
            <h2>Metadata dashboard</h2>
            {downloadUrl && (
              <a className="download-button" href={downloadUrl} download>
                <Download size={16} />
                Download edited file
              </a>
            )}
          </div>

          {!currentFile ? (
            <div className="empty-state">
              <HardDrive size={32} />
              <p>Select a file to inspect metadata.</p>
            </div>
          ) : (
            <>
              <div className="summary-grid">
                <div className="summary-card">
                  <FileImage size={18} />
                  <div>
                    <span>Media type</span>
                    <strong>{mediaType}</strong>
                  </div>
                </div>
                <div className="summary-card">
                  <FileText size={18} />
                  <div>
                    <span>Source file</span>
                    <strong>{currentFile}</strong>
                  </div>
                </div>
              </div>

              <div className="accordion-block">
                <button type="button" className="accordion-header" onClick={() => setExpanded((value) => ({ ...value, file: !value.file }))}>
                  <span>File Information</span>
                  {expanded.file ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
                </button>
                {expanded.file && (
                  <div className="field-grid">
                    {infoEntries.map(([key, value]) => (
                      <label key={key} className="field-item">
                        <span>{key}</span>
                        <input value={String(value || '')} readOnly />
                      </label>
                    ))}
                  </div>
                )}
              </div>

              <div className="accordion-block">
                <button type="button" className="accordion-header" onClick={() => setExpanded((value) => ({ ...value, metadata: !value.metadata }))}>
                  <span>Media Details</span>
                  {expanded.metadata ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
                </button>
                {expanded.metadata && (
                  <div className="field-grid">
                    {detailsEntries.map(([key, value]) => (
                      <label key={key} className="field-item">
                        <span>{key}</span>
                        <input value={String(value || '')} readOnly />
                      </label>
                    ))}
                  </div>
                )}
              </div>

              <div className="accordion-block">
                <button type="button" className="accordion-header" onClick={() => setExpanded((value) => ({ ...value, tags: !value.tags }))}>
                  <span>Metadata Tags</span>
                  {expanded.tags ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
                </button>
                {expanded.tags && (
                  <div className="field-grid">
                    {editableEntries.map(([key, value]) => (
                      <label key={key} className="field-item">
                        <span>{key}</span>
                        <input
                          value={String(value ?? '')}
                          onChange={(event) =>
                            setEditableFields((prev) => ({
                              ...prev,
                              [key]: event.target.value,
                            }))
                          }
                        />
                      </label>
                    ))}
                  </div>
                )}
              </div>
            </>
          )}
        </section>
      </main>

      <footer className="bottom-bar">
        <div className="save-note">
          {mediaType === 'image' ? <Camera size={16} /> : mediaType === 'video' ? <PlayCircle size={16} /> : <Music4 size={16} />}
          <span>Metadata-only edits preserve the original media streams.</span>
        </div>
        <button type="button" className="save-button" onClick={handleSubmit} disabled={!currentFile || loading}>
          <Save size={16} />
          {loading ? 'Saving...' : 'Save Metadata'}
        </button>
      </footer>
    </div>
  )
}

export default App
