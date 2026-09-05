"use client";
import { useEffect, useState } from "react";
import {
  DndContext, DragEndEvent, DragOverlay, DragStartEvent, useDroppable,
} from "@dnd-kit/core";
import { useDraggable } from "@dnd-kit/core";
import { getTrackedJobs, updateJobStatus, deleteJob } from "@/lib/api";
import ManualAddForm from "./ManualAddForm";

type TrackedJob = {
  id: string;
  company: string;
  title: string;
  url: string | null;
  location: string | null;
  status: string;
  comp_min: number | null;
  comp_max: number | null;
  comp_currency: string | null;
};

const COLUMNS = ["saved", "applied", "interviewing", "negotiating"] as const;
const COLUMN_LABELS: Record<string, string> = {
  saved: "Saved", applied: "Applied", interviewing: "Interviewing", negotiating: "Negotiating",
};
const TRASH_ID = "trash-zone";

function DraggableCard({ job }: { job: TrackedJob }) {
  const { attributes, listeners, setNodeRef, transform } = useDraggable({ id: job.id });
  const style = transform
    ? { transform: `translate3d(${transform.x}px, ${transform.y}px, 0)`, zIndex: 50 }
    : undefined;

  return (
    <div
      ref={setNodeRef}
      style={style}
      {...listeners}
      {...attributes}
      className="border rounded p-3 bg-white shadow-sm cursor-grab active:cursor-grabbing"
    >
      <p className="text-sm font-medium">{job.title}</p>
      <p className="text-xs text-gray-500">{job.company} · {job.location ?? "—"}</p>
      {job.comp_min && job.comp_max && (
        <p className="text-xs text-gray-600 mt-1">
          {job.comp_currency ?? "USD"} {job.comp_min.toLocaleString()}–{job.comp_max.toLocaleString()}
        </p>
      )}
    </div>
  );
}

function Column({ status, jobs }: { status: string; jobs: TrackedJob[] }) {
  const { setNodeRef, isOver } = useDroppable({ id: status });
  return (
    <div
      ref={setNodeRef}
      className={`flex-1 min-w-[220px] rounded-lg p-3 ${isOver ? "bg-blue-50" : "bg-gray-50"}`}
    >
      <h3 className="text-sm font-semibold mb-2">{COLUMN_LABELS[status]}</h3>
      <div className="flex flex-col gap-2">
        {jobs.filter((j) => j.status === status).map((job) => (
          <DraggableCard key={job.id} job={job} />
        ))}
      </div>
    </div>
  );
}

function TrashZone() {
  const { setNodeRef, isOver } = useDroppable({ id: TRASH_ID });
  return (
    <div
      ref={setNodeRef}
      className={`fixed bottom-6 right-6 w-16 h-16 rounded-full flex items-center justify-center text-white text-2xl ${
        isOver ? "bg-red-600" : "bg-gray-700"
      }`}
    >
      🗑
    </div>
  );
}

export default function KanbanBoard() {
  const [jobs, setJobs] = useState<TrackedJob[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);

  const load = async () => {
    const data = await getTrackedJobs();
    setJobs(data);
  };

  useEffect(() => {
    load();
  }, []);

  const handleDragStart = (event: DragStartEvent) => {
    setActiveId(event.active.id as string);
  };

  const handleDragEnd = async (event: DragEndEvent) => {
    const { active, over } = event;
    setActiveId(null);
    if (!over) return;

    const jobId = active.id as string;
    const targetId = over.id as string;

    if (targetId === TRASH_ID) {
      setJobs((prev) => prev.filter((j) => j.id !== jobId)); // optimistic
      await deleteJob(jobId);
      return;
    }

    if (COLUMNS.includes(targetId as typeof COLUMNS[number])) {
      setJobs((prev) => prev.map((j) => (j.id === jobId ? { ...j, status: targetId } : j))); // optimistic
      await updateJobStatus(jobId, targetId);
    }
  };

  const activeJob = jobs.find((j) => j.id === activeId);

  return (
    <div className="p-6">
      <ManualAddForm onAdded={load} />
      <DndContext onDragStart={handleDragStart} onDragEnd={handleDragEnd}>
        <div className="flex gap-4 overflow-x-auto">
          {COLUMNS.map((status) => (
            <Column key={status} status={status} jobs={jobs} />
          ))}
        </div>
        <TrashZone />
        <DragOverlay>
          {activeJob && <DraggableCard job={activeJob} />}
        </DragOverlay>
      </DndContext>
    </div>
  );
}