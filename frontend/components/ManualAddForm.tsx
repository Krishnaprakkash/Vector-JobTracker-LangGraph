"use client";
import { useEffect, useState } from "react";
import { getResumes, addManualJob } from "@/lib/api";

type Resume = { id: string; filename: string };

export default function ManualAddForm({ onAdded }: { onAdded: () => void }) {
  const [open, setOpen] = useState(false);
  const [resumes, setResumes] = useState<Resume[]>([]);
  const [form, setForm] = useState({
    company: "", title: "", location: "", resume_id: "", raw_input: "",
    comp_min: "", comp_max: "", comp_currency: "USD",
  });
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (open) getResumes().then(setResumes);
  }, [open]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    await addManualJob({
      company: form.company,
      title: form.title,
      location: form.location,
      resume_id: form.resume_id,
      raw_input: form.raw_input,
      comp_min: form.comp_min ? Number(form.comp_min) : undefined,
      comp_max: form.comp_max ? Number(form.comp_max) : undefined,
      comp_currency: form.comp_currency,
    });
    setSubmitting(false);
    setOpen(false);
    setForm({ company: "", title: "", location: "", resume_id: "", raw_input: "", comp_min: "", comp_max: "", comp_currency: "USD" });
    onAdded();
  };

  if (!open) {
    return (
      <button onClick={() => setOpen(true)} className="px-4 py-2 border rounded text-sm">
        + Add Job Manually
      </button>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="border rounded-lg p-4 bg-white flex flex-col gap-3 max-w-md">
      <input required placeholder="Company" value={form.company}
        onChange={(e) => setForm({ ...form, company: e.target.value })}
        className="border rounded px-3 py-2 text-sm" />
      <input required placeholder="Title" value={form.title}
        onChange={(e) => setForm({ ...form, title: e.target.value })}
        className="border rounded px-3 py-2 text-sm" />
      <input required placeholder="Location" value={form.location}
        onChange={(e) => setForm({ ...form, location: e.target.value })}
        className="border rounded px-3 py-2 text-sm" />

      <select required value={form.resume_id} onChange={(e) => setForm({ ...form, resume_id: e.target.value })}
        className="border rounded px-3 py-2 text-sm">
        <option value="">Select resume</option>
        {resumes.map((r) => <option key={r.id} value={r.id}>{r.filename}</option>)}
      </select>

      <textarea required placeholder="Paste job URL or description text" value={form.raw_input}
        onChange={(e) => setForm({ ...form, raw_input: e.target.value })}
        className="border rounded px-3 py-2 text-sm h-24" />

      <div className="flex gap-2">
        <input placeholder="Comp min" type="number" value={form.comp_min}
          onChange={(e) => setForm({ ...form, comp_min: e.target.value })}
          className="border rounded px-3 py-2 text-sm flex-1" />
        <input placeholder="Comp max" type="number" value={form.comp_max}
          onChange={(e) => setForm({ ...form, comp_max: e.target.value })}
          className="border rounded px-3 py-2 text-sm flex-1" />
      </div>

      <div className="flex gap-2">
        <button type="submit" disabled={submitting} className="px-4 py-2 bg-black text-white rounded text-sm disabled:opacity-50">
          {submitting ? "Adding..." : "Add Job"}
        </button>
        <button type="button" onClick={() => setOpen(false)} className="px-4 py-2 border rounded text-sm">
          Cancel
        </button>
      </div>
    </form>
  );
}