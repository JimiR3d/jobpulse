/**
 * frontend/src/pages/Profile.jsx
 *
 * Resume upload + skill editing + preference sliders + Telegram link flow.
 */

import { useEffect, useState, useRef } from 'react'
import { Upload, X, Plus, Bot, Check, RefreshCw, Unlink } from 'lucide-react'
import { profileApi, telegramApi } from '../lib/api'
import { supabase } from '../lib/supabase'

export default function Profile() {
  const [profile, setProfile] = useState(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [autoGenerating, setAutoGenerating] = useState(false)

  // Form state
  const [nlDesc, setNlDesc] = useState('')
  const [skills, setSkills] = useState([])
  const [newSkill, setNewSkill] = useState('')
  const [minScore, setMinScore] = useState(55)
  const [notifThreshold, setNotifThreshold] = useState(70)
  const [showSenior, setShowSenior] = useState(false)
  const [seniorityLevels, setSeniorityLevels] = useState(['internship', 'entry', 'junior'])

  // Resume upload state
  const [uploading, setUploading] = useState(false)
  const [uploadResult, setUploadResult] = useState(null)
  const [dragOver, setDragOver] = useState(false)
  const fileInputRef = useRef(null)

  // Telegram state
  const [telegramStatus, setTelegramStatus] = useState(null)
  const [linkCode, setLinkCode] = useState('')
  const [verifying, setVerifying] = useState(false)
  const [linkSuccess, setLinkSuccess] = useState(false)

  useEffect(() => {
    loadProfile()
    loadTelegramStatus()
  }, [])

  async function loadProfile() {
    setLoading(true)
    try {
      const data = await profileApi.get()
      setProfile(data)
      const p = Array.isArray(data.user_profiles) ? (data.user_profiles[0] || {}) : (data.user_profiles || {})
      setNlDesc(p.natural_language_description || '')
      setSkills(p.skills || [])
      setMinScore(p.min_display_score || 55)
      setShowSenior(p.show_senior || false)
      setSeniorityLevels(p.seniority_levels || ['internship', 'entry', 'junior'])
      setNotifThreshold(data.notification_threshold || 70)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  async function loadTelegramStatus() {
    try {
      const data = await telegramApi.status()
      setTelegramStatus(data)
    } catch (e) {
      console.error(e)
    }
  }

  async function handleSave() {
    setSaving(true)
    try {
      await profileApi.update({
        natural_language_description: nlDesc,
        skills,
        min_display_score: minScore,
        show_senior: showSenior,
        seniority_levels: seniorityLevels,
        notification_threshold: notifThreshold,
      })
      // Show saved feedback briefly
      setSaving('saved')
      setTimeout(() => setSaving(false), 2000)
    } catch (e) {
      alert('Save failed: ' + e.message)
      setSaving(false)
    }
  }

  async function handleResumeUpload(file) {
    if (!file || !file.name.endsWith('.pdf')) {
      alert('Please upload a PDF file')
      return
    }
    setUploading(true)
    setUploadResult(null)
    try {
      const result = await profileApi.uploadResume(file)
      setUploadResult(result.parsed)
      
      const newSkills = result.parsed.skills || skills
      setSkills(newSkills)
      
      // Auto-save so they don't vanish if the user leaves
      await profileApi.update({
        skills: newSkills,
        target_roles: result.parsed.inferred_roles || [],
      })
    } catch (e) {
      alert('Upload failed: ' + e.message)
    } finally {
      setUploading(false)
    }
  }

  function handleDrop(e) {
    e.preventDefault()
    setDragOver(false)
    const file = e.dataTransfer?.files[0]
    if (file) handleResumeUpload(file)
  }

  async function handleAutoGenerate() {
    setAutoGenerating(true)
    try {
      const res = await profileApi.generateDescription(skills, seniorityLevels)
      setNlDesc(res.description)
    } catch (e) {
      alert('AI Generation failed: ' + e.message)
    } finally {
      setAutoGenerating(false)
    }
  }

  function addSkill() {
    const s = newSkill.trim()
    if (s && !skills.includes(s)) {
      setSkills([...skills, s])
    }
    setNewSkill('')
  }

  function removeSkill(skill) {
    setSkills(skills.filter(s => s !== skill))
  }

  function toggleSeniority(level) {
    setSeniorityLevels(prev =>
      prev.includes(level) ? prev.filter(l => l !== level) : [...prev, level]
    )
  }

  async function handleVerifyCode() {
    if (linkCode.length !== 6) return
    setVerifying(true)
    try {
      await telegramApi.verify(linkCode)
      setLinkSuccess(true)
      setLinkCode('')
      await loadTelegramStatus()
    } catch (e) {
      alert('Invalid or expired code. Send /start to the bot again.')
    } finally {
      setVerifying(false)
    }
  }

  async function handleUnlink() {
    if (!confirm('Unlink your Telegram account?')) return
    try {
      await telegramApi.unlink()
      setTelegramStatus({ linked: false })
      setLinkSuccess(false)
    } catch (e) {
      alert('Unlink failed: ' + e.message)
    }
  }

  const SENIORITY_OPTIONS = [
    { id: 'internship', label: '🎓 Internship' },
    { id: 'entry',      label: '🟢 Entry-level' },
    { id: 'junior',     label: '🔵 Junior' },
    { id: 'mid',        label: 'Mid-level' },
  ]

  if (loading) {
    return (
      <div className="flex justify-center py-20">
        <div className="spinner w-8 h-8" />
      </div>
    )
  }

  return (
    <div className="p-6 max-w-2xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-100">Profile</h1>
        <p className="text-sm text-gray-400 mt-0.5">
          Your resume and preferences shape every AI match score
        </p>
      </div>

      {/* Resume upload */}
      <div className="card">
        <h2 className="section-title mb-1">Resume</h2>
        <p className="section-subtitle mb-4">Upload a PDF — AI will extract your skills and experience automatically</p>

        <div
          className={`border-2 border-dashed rounded-xl p-8 text-center transition-all duration-200 cursor-pointer
            ${dragOver ? 'border-brand-500 bg-brand-900/20' : 'border-gray-700 hover:border-gray-600'}`}
          onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
          onDragLeave={() => setDragOver(false)}
          onDrop={handleDrop}
          onClick={() => fileInputRef.current?.click()}
        >
          {uploading ? (
            <div className="flex flex-col items-center gap-2">
              <RefreshCw size={28} className="text-brand-400 animate-spin" />
              <p className="text-sm text-gray-400">Parsing your resume…</p>
            </div>
          ) : (
            <div className="flex flex-col items-center gap-2">
              <Upload size={28} className="text-gray-500" />
              <p className="text-sm text-gray-300">
                Drop PDF here or <span className="text-brand-400">click to browse</span>
              </p>
              <p className="text-xs text-gray-600">PDF only · Max 5MB</p>
            </div>
          )}
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf"
            className="hidden"
            onChange={e => e.target.files[0] && handleResumeUpload(e.target.files[0])}
          />
        </div>

        {uploadResult && (
          <div className="mt-4 p-4 bg-emerald-900/20 border border-emerald-800/50 rounded-xl animate-in">
            <p className="text-sm font-semibold text-emerald-300 mb-2">✅ Resume parsed!</p>
            {uploadResult.education && (
              <p className="text-xs text-gray-400">🎓 {uploadResult.education}</p>
            )}
            {uploadResult.experience_years != null && (
              <p className="text-xs text-gray-400">💼 {uploadResult.experience_years} years experience</p>
            )}
            {uploadResult.inferred_roles?.length > 0 && (
              <div className="mt-2">
                <p className="text-xs text-gray-500 mb-1">Suggested roles:</p>
                <div className="flex flex-wrap gap-1">
                  {uploadResult.inferred_roles.map(r => (
                    <span key={r} className="badge badge-blue text-xs">{r}</span>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Skills */}
      <div className="card">
        <h2 className="section-title mb-1">Skills</h2>
        <p className="section-subtitle mb-4">
          These are matched against every job's required stack
        </p>
        <div className="flex flex-wrap gap-2 mb-3">
          {skills.map(skill => (
            <span key={skill} className="badge badge-blue group">
              {skill}
              <button
                onClick={() => removeSkill(skill)}
                className="ml-1 text-blue-400 hover:text-red-400 transition-colors"
              >
                <X size={10} />
              </button>
            </span>
          ))}
          {skills.length === 0 && (
            <p className="text-sm text-gray-500">No skills yet — upload your resume to auto-populate</p>
          )}
        </div>
        <div className="flex gap-2">
          <input
            className="input flex-1"
            placeholder="Add a skill (e.g. Python, React, SQL)"
            value={newSkill}
            onChange={e => setNewSkill(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && addSkill()}
          />
          <button className="btn btn-secondary" onClick={addSkill}>
            <Plus size={14} />
          </button>
        </div>
      </div>

      {/* Natural language description */}
      <div className="card">
        <div className="flex justify-between items-start mb-1">
          <h2 className="section-title">What I'm Looking For</h2>
          <button
            onClick={handleAutoGenerate}
            disabled={autoGenerating}
            className="btn btn-sm btn-secondary text-brand-400 hover:text-brand-300 border-brand-900/50"
          >
            {autoGenerating ? <RefreshCw size={12} className="animate-spin mr-1" /> : <Bot size={12} className="mr-1" />}
            Auto-write with AI
          </button>
        </div>
        <p className="section-subtitle mb-4">
          Plain English description — used by Gemini to score every job against your goals
        </p>
        <textarea
          className="textarea h-28"
          placeholder={`e.g. "I'm a CS grad in Lagos looking for entry-level or internship roles in data analysis, backend dev, or product. Willing to be trained. Prefer USD/GBP/EUR pay. No country restrictions."`}
          value={nlDesc}
          onChange={e => setNlDesc(e.target.value)}
          maxLength={1000}
        />
        <p className="text-xs text-gray-600 mt-1 text-right">{nlDesc.length}/1000</p>
      </div>

      {/* Preferences */}
      <div className="card space-y-5">
        <h2 className="section-title">Preferences</h2>

        {/* Seniority checkboxes */}
        <div>
          <label className="text-sm font-medium text-gray-300 block mb-2">
            Seniority levels to show
          </label>
          <div className="flex flex-wrap gap-2">
            {SENIORITY_OPTIONS.map(opt => (
              <button
                key={opt.id}
                onClick={() => toggleSeniority(opt.id)}
                className={`btn btn-sm ${
                  seniorityLevels.includes(opt.id) ? 'btn-primary' : 'btn-secondary'
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>

        {/* Min display score */}
        <div>
          <label className="text-sm font-medium text-gray-300 block mb-2">
            Minimum display score: <span className="text-brand-400 font-mono">{minScore}</span>
          </label>
          <input
            type="range" min={0} max={100} step={5}
            value={minScore}
            onChange={e => setMinScore(+e.target.value)}
            className="w-full accent-brand-500"
          />
          <div className="flex justify-between text-xs text-gray-600 mt-1">
            <span>Show all</span>
            <span>Only top matches</span>
          </div>
        </div>

        {/* Telegram threshold */}
        <div>
          <label className="text-sm font-medium text-gray-300 block mb-2">
            Telegram alert threshold: <span className="text-brand-400 font-mono">{notifThreshold}</span>
          </label>
          <input
            type="range" min={0} max={100} step={5}
            value={notifThreshold}
            onChange={e => setNotifThreshold(+e.target.value)}
            className="w-full accent-brand-500"
          />
          <p className="text-xs text-gray-500 mt-1">
            You'll receive Telegram alerts for jobs scoring above this threshold
          </p>
        </div>

        {/* Show senior toggle */}
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-gray-300">Show senior & lead roles</p>
            <p className="text-xs text-gray-500">Includes senior/lead in your main feed</p>
          </div>
          <button
            onClick={() => setShowSenior(!showSenior)}
            className={`toggle-track ${showSenior ? 'toggle-track-on' : ''}`}
          >
            <span className={`toggle-thumb ${showSenior ? 'toggle-thumb-on' : ''}`} />
          </button>
        </div>
      </div>

      {/* Telegram linking */}
      <div className="card">
        <div className="flex items-center gap-2 mb-1">
          <Bot size={18} className="text-sky-400" />
          <h2 className="section-title">Telegram Alerts</h2>
        </div>

        {telegramStatus?.linked || linkSuccess ? (
          <div className="space-y-3">
            <div className="flex items-center gap-2 text-emerald-300">
              <Check size={16} />
              <p className="text-sm font-medium">Telegram linked!</p>
            </div>
            <p className="text-xs text-gray-500">
              Alert threshold: {telegramStatus?.notification_threshold ?? notifThreshold}/100 ·
              Frequency: {telegramStatus?.notification_frequency ?? 'realtime'}
            </p>
            <button className="btn btn-danger btn-sm" onClick={handleUnlink}>
              <Unlink size={14} />
              Unlink Telegram
            </button>
          </div>
        ) : (
          <div className="space-y-4">
            <p className="text-sm text-gray-400">
              Send <code className="text-brand-300 bg-gray-800 px-1 rounded">/start</code> to{' '}
              <a
                href="https://t.me/JobPulseBot"
                target="_blank"
                rel="noopener noreferrer"
                className="text-sky-400 hover:text-sky-300"
              >
                @JobPulseBot
              </a>{' '}
              on Telegram, then enter the 6-digit code below:
            </p>
            <div className="flex gap-2">
              <input
                className="input font-mono text-center tracking-widest text-lg w-40"
                placeholder="000000"
                maxLength={6}
                value={linkCode}
                onChange={e => setLinkCode(e.target.value.replace(/\D/g, ''))}
                onKeyDown={e => e.key === 'Enter' && handleVerifyCode()}
              />
              <button
                className="btn btn-primary"
                onClick={handleVerifyCode}
                disabled={linkCode.length !== 6 || verifying}
              >
                {verifying ? (
                  <RefreshCw size={14} className="animate-spin" />
                ) : 'Link Account'}
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Save button */}
      <div className="flex justify-end pb-8">
        <button
          className="btn btn-primary px-8"
          onClick={handleSave}
          disabled={saving === true}
        >
          {saving === 'saved' ? (
            <><Check size={14} /> Saved!</>
          ) : saving ? (
            <><RefreshCw size={14} className="animate-spin" /> Saving…</>
          ) : 'Save Changes'}
        </button>
      </div>
    </div>
  )
}
