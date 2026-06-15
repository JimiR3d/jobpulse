/**
 * frontend/src/pages/Sources.jsx
 *
 * Two tabs:
 * 1. Job Boards Library — grid of all pre-loaded sources with toggles
 * 2. Custom Sources — bulk URL paste + GitHub README parser
 */

import { useEffect, useState } from 'react'
import { GitBranch, Upload, RefreshCw, CheckSquare, Square, Plus } from 'lucide-react'
import SourceCard from '../components/SourceCard'
import { sourcesApi, importsApi } from '../lib/api'

const TABS = ['Library', 'Bulk Import', 'GitHub Parser']

export default function Sources() {
  const [activeTab, setActiveTab] = useState('Library')
  const [sources, setSources] = useState({ library: [], custom: [] })
  const [categories, setCategories] = useState([])
  const [selectedCategory, setSelectedCategory] = useState(null)
  const [loading, setLoading] = useState(true)

  // Bulk import state
  const [bulkText, setBulkText] = useState('')
  const [bulkResults, setBulkResults] = useState(null)
  const [bulkLoading, setBulkLoading] = useState(false)
  const [selectedValid, setSelectedValid] = useState([])

  // GitHub parser state
  const [githubUrl, setGithubUrl] = useState('')
  const [githubResults, setGithubResults] = useState(null)
  const [githubLoading, setGithubLoading] = useState(false)
  const [selectedBoards, setSelectedBoards] = useState([])

  useEffect(() => {
    loadSources()
  }, [])

  async function loadSources() {
    setLoading(true)
    try {
      const [srcData, catData] = await Promise.all([
        sourcesApi.getAll(),
        sourcesApi.getCategories(),
      ])
      setSources(srcData)
      setCategories(catData.categories || [])
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  // ── Library tab ─────────────────────────────────────────────
  const filteredLibrary = selectedCategory
    ? sources.library.filter(s => s.category === selectedCategory)
    : sources.library

  // ── Bulk import tab ─────────────────────────────────────────
  async function handleBulkValidate() {
    setBulkLoading(true)
    setBulkResults(null)
    setSelectedValid([])
    try {
      const result = await importsApi.bulk(bulkText)
      setBulkResults(result)
      setSelectedValid(result.valid.map(v => v.url))
    } catch (e) {
      alert('Validation failed: ' + e.message)
    } finally {
      setBulkLoading(false)
    }
  }

  async function handleBulkActivate() {
    const toActivate = bulkResults.valid.filter(v => selectedValid.includes(v.url))
    if (!toActivate.length) return
    try {
      await importsApi.activate(toActivate)
      setBulkResults(null)
      setBulkText('')
      setSelectedValid([])
      await loadSources()
      alert(`✅ ${toActivate.length} sources activated!`)
    } catch (e) {
      alert('Activation failed: ' + e.message)
    }
  }

  // ── GitHub parser tab ──────────────────────────────────────
  async function handleGithubParse() {
    setGithubLoading(true)
    setGithubResults(null)
    setSelectedBoards([])
    try {
      const result = await importsApi.github(githubUrl)
      setGithubResults(result)
      setSelectedBoards(
        result.boards.filter(b => !b.is_duplicate).map(b => b.url)
      )
    } catch (e) {
      alert('Parse failed: ' + e.message)
    } finally {
      setGithubLoading(false)
    }
  }

  async function handleGithubActivate() {
    const toActivate = githubResults.boards
      .filter(b => selectedBoards.includes(b.url))
      .map(b => ({ url: b.url, name: b.name, source_type: 'jina', category: b.category || 'General' }))
    if (!toActivate.length) return
    try {
      await importsApi.activate(toActivate)
      setGithubResults(null)
      setGithubUrl('')
      setSelectedBoards([])
      await loadSources()
      alert(`✅ ${toActivate.length} sources activated!`)
    } catch (e) {
      alert('Activation failed: ' + e.message)
    }
  }

  function toggleBoard(url) {
    setSelectedBoards(prev =>
      prev.includes(url) ? prev.filter(u => u !== url) : [...prev, url]
    )
  }

  function toggleValid(url) {
    setSelectedValid(prev =>
      prev.includes(url) ? prev.filter(u => u !== url) : [...prev, url]
    )
  }

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-100">Job Sources</h1>
        <p className="text-sm text-gray-400 mt-0.5">
          Manage which job boards the scheduler monitors
        </p>
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-1 mb-6 bg-gray-900 p-1 rounded-xl w-fit">
        {TABS.map(tab => (
          <button
            key={tab}
            className={activeTab === tab ? 'tab-active' : 'tab'}
            onClick={() => setActiveTab(tab)}
          >
            {tab}
          </button>
        ))}
      </div>

      {/* ── Library Tab ── */}
      {activeTab === 'Library' && (
        <div>
          {/* Category filter */}
          <div className="flex items-center gap-2 mb-4 flex-wrap">
            <button
              className={!selectedCategory ? 'tab-active' : 'tab'}
              onClick={() => setSelectedCategory(null)}
            >
              All ({sources.library.length})
            </button>
            {categories.map(cat => (
              <button
                key={cat}
                className={selectedCategory === cat ? 'tab-active' : 'tab'}
                onClick={() => setSelectedCategory(cat)}
              >
                {cat}
              </button>
            ))}
          </div>

          {loading ? (
            <div className="flex justify-center py-20">
              <div className="spinner w-8 h-8" />
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {filteredLibrary.map(source => (
                <SourceCard key={source.id} source={source} />
              ))}
            </div>
          )}

          {/* Custom sources section */}
          {sources.custom.length > 0 && (
            <div className="mt-8">
              <h2 className="section-title mb-3">Your Custom Sources</h2>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {sources.custom.map(source => (
                  <SourceCard key={source.id} source={source} />
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── Bulk Import Tab ── */}
      {activeTab === 'Bulk Import' && (
        <div className="space-y-4">
          <div className="card">
            <h2 className="section-title mb-1">Paste URLs</h2>
            <p className="section-subtitle mb-4">
              One URL per line. We'll validate each one and detect whether it's an RSS feed or a scrapeable page.
            </p>
            <textarea
              className="textarea h-40 font-mono text-xs"
              placeholder={`https://example-job-board.com/remote\nhttps://another-board.com/jobs/rss\nhttps://...`}
              value={bulkText}
              onChange={e => setBulkText(e.target.value)}
            />
            <div className="mt-3 flex items-center gap-2">
              <button
                className="btn btn-primary"
                onClick={handleBulkValidate}
                disabled={!bulkText.trim() || bulkLoading}
              >
                {bulkLoading ? (
                  <><RefreshCw size={14} className="animate-spin" /> Validating…</>
                ) : (
                  <><Upload size={14} /> Validate URLs</>
                )}
              </button>
              {bulkText && (
                <span className="text-xs text-gray-500">
                  {bulkText.split('\n').filter(l => l.trim()).length} URLs
                </span>
              )}
            </div>
          </div>

          {/* Results */}
          {bulkResults && (
            <div className="card space-y-4 animate-in">
              <div className="flex items-center gap-4 flex-wrap">
                <span className="badge badge-green">✓ {bulkResults.valid.length} valid</span>
                <span className="badge badge-gray">{bulkResults.duplicates.length} duplicates</span>
                <span className="badge badge-orange">{bulkResults.no_jobs.length} no jobs found</span>
                <span className="badge-gray badge">{bulkResults.errors.length} errors</span>
              </div>

              {bulkResults.valid.length > 0 && (
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <p className="text-sm font-semibold text-gray-300">Valid — select to activate:</p>
                    <button
                      className="btn btn-ghost btn-sm"
                      onClick={() =>
                        setSelectedValid(
                          selectedValid.length === bulkResults.valid.length
                            ? []
                            : bulkResults.valid.map(v => v.url)
                        )
                      }
                    >
                      {selectedValid.length === bulkResults.valid.length ? 'Deselect all' : 'Select all'}
                    </button>
                  </div>
                  <div className="space-y-2">
                    {bulkResults.valid.map(v => (
                      <label key={v.url} className="flex items-center gap-3 cursor-pointer group">
                        <button onClick={() => toggleValid(v.url)} className="text-brand-400">
                          {selectedValid.includes(v.url)
                            ? <CheckSquare size={16} />
                            : <Square size={16} className="text-gray-600" />}
                        </button>
                        <div className="flex-1 min-w-0">
                          <span className="text-sm text-gray-200 font-medium">{v.name}</span>
                          <span className="text-xs text-gray-500 ml-2 truncate">{v.url}</span>
                        </div>
                        <span className="badge badge-gray text-xs">{v.source_type}</span>
                      </label>
                    ))}
                  </div>

                  <button
                    className="btn btn-primary mt-4"
                    onClick={handleBulkActivate}
                    disabled={!selectedValid.length}
                  >
                    <Plus size={14} />
                    Activate {selectedValid.length} selected
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* ── GitHub Parser Tab ── */}
      {activeTab === 'GitHub Parser' && (
        <div className="space-y-4">
          <div className="card">
            <div className="flex items-center gap-2 mb-1">
              <GitBranch size={18} className="text-gray-400" />
              <h2 className="section-title">GitHub README Parser</h2>
            </div>
            <p className="section-subtitle mb-4">
              Paste any GitHub repo URL (e.g. awesome-remote-job). We'll extract all job board URLs from the README using AI.
            </p>
            <div className="flex gap-2">
              <input
                className="input flex-1"
                placeholder="https://github.com/lukasz-madon/awesome-remote-job"
                value={githubUrl}
                onChange={e => setGithubUrl(e.target.value)}
              />
              <button
                className="btn btn-primary"
                onClick={handleGithubParse}
                disabled={!githubUrl.trim() || githubLoading}
              >
                {githubLoading ? (
                  <RefreshCw size={14} className="animate-spin" />
                ) : (
                  'Extract'
                )}
              </button>
            </div>
          </div>

          {githubResults && (
            <div className="card animate-in space-y-4">
              <div className="flex items-center gap-3">
                <span className="section-title">{githubResults.repo}</span>
                <span className="badge badge-blue">{githubResults.total_found} boards found</span>
                <span className="badge badge-green">{githubResults.new_count} new</span>
              </div>

              {githubResults.boards.length > 0 && (
                <>
                  <div className="flex items-center justify-between">
                    <p className="text-sm text-gray-400">Select boards to activate:</p>
                    <button
                      className="btn btn-ghost btn-sm"
                      onClick={() =>
                        setSelectedBoards(
                          selectedBoards.length ===
                            githubResults.boards.filter(b => !b.is_duplicate).length
                            ? []
                            : githubResults.boards.filter(b => !b.is_duplicate).map(b => b.url)
                        )
                      }
                    >
                      Toggle all new
                    </button>
                  </div>

                  <div className="space-y-2 max-h-80 overflow-y-auto pr-1">
                    {githubResults.boards.map(board => (
                      <label
                        key={board.url}
                        className={`flex items-center gap-3 cursor-pointer ${
                          board.is_duplicate ? 'opacity-40 cursor-not-allowed' : ''
                        }`}
                      >
                        <button
                          onClick={() => !board.is_duplicate && toggleBoard(board.url)}
                          className="text-brand-400 shrink-0"
                          disabled={board.is_duplicate}
                        >
                          {selectedBoards.includes(board.url)
                            ? <CheckSquare size={16} />
                            : <Square size={16} className="text-gray-600" />}
                        </button>
                        <div className="flex-1 min-w-0">
                          <span className="text-sm text-gray-200 font-medium">{board.name}</span>
                          <span className="text-xs text-gray-500 ml-2 truncate block">{board.url}</span>
                        </div>
                        <div className="flex items-center gap-1">
                          {board.category && (
                            <span className="badge badge-gray text-xs">{board.category}</span>
                          )}
                          {board.is_duplicate && (
                            <span className="badge badge-gray text-xs">Already added</span>
                          )}
                        </div>
                      </label>
                    ))}
                  </div>

                  <button
                    className="btn btn-primary"
                    onClick={handleGithubActivate}
                    disabled={!selectedBoards.length}
                  >
                    <Plus size={14} />
                    Activate {selectedBoards.length} boards
                  </button>
                </>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
